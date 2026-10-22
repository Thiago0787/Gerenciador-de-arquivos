import os
import shutil
import re
import urllib.request
import webbrowser
import threading
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
from PIL import Image, ImageTk

# Importa o motor e as configurações centralizadas[cite: 1, 2]
import nomeador
from configuracoes import (
    CATEGORIAS_DOCUMENTOS,
    carregar_configuracoes,
    salvar_configuracoes,
    gerar_caminho_unico
)

VERSAO_ATUAL = "1.0.0"
URL_VERSAO_GITHUB = "https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPOSITORIO/main/versao.json"

def verificar_atualizacoes():
    try:
        req = urllib.request.Request(URL_VERSAO_GITHUB, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as resposta:
            import json
            dados = json.loads(resposta.read().decode('utf-8'))
            versao_remota = dados.get("versao")
            url_download = dados.get("download_url")

            if versao_remota and versao_remota != VERSAO_ATUAL:
                resposta_user = messagebox.askyesno(
                    "Nova Atualização!",
                    f"A versão {versao_remota} está disponível! (Versão atual: {VERSAO_ATUAL})\n\nDeseja baixar a nova versão agora?"
                )
                if resposta_user:
                    webbrowser.open(url_download)
    except Exception:
        pass


class AppVerificador:
    def __init__(self, root, pasta_raiz):
        self.root = root
        self.pasta_raiz = pasta_raiz
        self.arquivos = []
        self.indice_atual = 0

        self.img_original = None
        self.img_tk = None
        self.escala = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.drag_data = {"x": 0, "y": 0}
        self.extensao_atual = ""

        self.lista_categorias = CATEGORIAS_DOCUMENTOS

        self.root.title("Verificador de Documentos")
        self.root.geometry("1100x750")
        self.root.configure(bg="#f4f4f4")

        self.lbl_aluno = tk.Label(root, text="A procurar documentos...", font=("Arial", 14, "bold"), bg="#f4f4f4", fg="#2c3e50")
        self.lbl_aluno.pack(pady=10)

        self.canvas = tk.Canvas(root, bg="#e0e0e0", cursor="hand2")
        self.canvas.pack(pady=5, expand=True, fill=tk.BOTH, padx=20)

        self.canvas.bind("<ButtonPress-1>", self.iniciar_arrasto)
        self.canvas.bind("<B1-Motion>", self.arrastar)
        self.canvas.bind("<MouseWheel>", self.zoom) 
        self.canvas.bind("<Button-4>", self.zoom) 
        self.canvas.bind("<Button-5>", self.zoom) 

        frame_controles = tk.Frame(root, bg="#f4f4f4")
        frame_controles.pack(side=tk.BOTTOM, pady=20)

        self.btn_voltar = tk.Button(frame_controles, text="<< Voltar", width=10, font=("Arial", 10, "bold"), bg="#cccccc", command=self.voltar)
        self.btn_voltar.grid(row=0, column=0, padx=10, ipady=5)

        self.btn_rodar = tk.Button(frame_controles, text="↻ Rodar", width=10, font=("Arial", 10, "bold"), bg="#3498db", fg="white", command=self.rodar_imagem)
        self.btn_rodar.grid(row=0, column=1, padx=10, ipady=5)

        self.btn_manter = tk.Button(frame_controles, text="Manter / Salvar", width=15, font=("Arial", 10, "bold"), command=self.manter)
        self.btn_manter.grid(row=0, column=2, padx=10, ipady=5)

        frame_nome = tk.Frame(frame_controles, bg="#f4f4f4")
        frame_nome.grid(row=0, column=3, padx=10)

        self.var_nome = tk.StringVar()
        self.opcoes_visiveis = []
        self.popup_autocomplete = None
        self.lista_autocomplete = None

        self.combo_nome = tk.Entry(frame_nome, textvariable=self.var_nome, width=32, font=("Arial", 12), relief=tk.SOLID, bd=1)
        self.combo_nome.pack(side=tk.LEFT, ipady=5)

        self.lbl_extensao = tk.Label(frame_nome, text="", font=("Arial", 12, "bold"), bg="#f4f4f4", fg="#7f8c8d")
        self.lbl_extensao.pack(side=tk.LEFT, padx=(2, 0))

        self.combo_nome.bind("<Button-1>", self.mostrar_todas_opcoes)
        self.combo_nome.bind("<FocusIn>", self.mostrar_todas_opcoes)
        self.combo_nome.bind("<KeyRelease>", self.filtrar_opcoes)
        self.combo_nome.bind("<Return>", self.autocomplete_enter)
        self.combo_nome.bind("<Escape>", self.fechar_autocomplete)
        self.combo_nome.bind("<Up>", self.autocomplete_cima)
        self.combo_nome.bind("<Down>", self.autocomplete_baixo)
        self.combo_nome.bind("<FocusOut>", self.autocomplete_focus_out)

        self.btn_deletar = tk.Button(frame_controles, text="Lixeira", width=10, bg="#ff4d4d", fg="white", font=("Arial", 10, "bold"), command=self.deletar)
        self.btn_deletar.grid(row=0, column=4, padx=10, ipady=5)

        self.root.protocol("WM_DELETE_WINDOW", self.fechar_janela)
        self.carregar_arquivos()

    def fechar_janela(self):
        self.fechar_autocomplete()
        if self.img_original:
            try:
                self.img_original.close()
            except Exception:
                pass
        self.root.destroy()

    def mostrar_todas_opcoes(self, event=None):
        def abrir():
            if self.root.focus_get() not in (self.combo_nome, self.lista_autocomplete):
                return
            self.opcoes_visiveis = list(self.lista_categorias)
            self.mostrar_autocomplete()
        self.root.after_idle(abrir)

    def filtrar_opcoes(self, event=None):
        if event and event.keysym in ("Up", "Down", "Left", "Right", "Return", "Escape", "Tab"):
            return "break"
        digitado = self.var_nome.get().strip()
        if not digitado:
            self.fechar_autocomplete()
            return
        texto = digitado.lower()
        self.opcoes_visiveis = [nome for nome in self.lista_categorias if texto in nome.lower()]
        if self.opcoes_visiveis:
            self.mostrar_autocomplete()
        else:
            self.fechar_autocomplete()

    def mostrar_autocomplete(self):
        if self.popup_autocomplete is None or not self.popup_autocomplete.winfo_exists():
            self.popup_autocomplete = tk.Toplevel(self.root)
            self.popup_autocomplete.overrideredirect(True)
            self.popup_autocomplete.transient(self.root)
            self.lista_autocomplete = tk.Listbox(
                self.popup_autocomplete, font=("Arial", 11), activestyle="none", 
                selectmode=tk.SINGLE, relief=tk.SOLID, bd=1, highlightthickness=1, height=1
            )
            self.lista_autocomplete.pack(fill=tk.BOTH, expand=True)
            self.lista_autocomplete.bind("<ButtonRelease-1>", self.selecionar_autocomplete)
            self.lista_autocomplete.bind("<Motion>", self.autocomplete_mouse_move)

        self.lista_autocomplete.delete(0, tk.END)
        for opcao in self.opcoes_visiveis:
            self.lista_autocomplete.insert(tk.END, opcao)

        if self.opcoes_visiveis:
            self.lista_autocomplete.selection_set(0)
            self.lista_autocomplete.activate(0)

        self.root.update_idletasks()
        self.popup_autocomplete.update_idletasks()
        x = self.combo_nome.winfo_rootx()
        campo_y = self.combo_nome.winfo_rooty()
        campo_altura = self.combo_nome.winfo_height()
        largura = self.combo_nome.winfo_width()
        altura = min(len(self.opcoes_visiveis), 8) * 27 + 4
        y = campo_y - altura

        topo_tela = self.root.winfo_vrooty()
        if y < topo_tela:
            y = campo_y + campo_altura

        self.popup_autocomplete.geometry(f"{largura}x{altura}+{x}+{y}")
        self.popup_autocomplete.lift()
        self.combo_nome.focus_set()

    def selecionar_autocomplete(self, event=None):
        if not self.lista_autocomplete:
            return "break"
        selecao = self.lista_autocomplete.curselection()
        if not selecao:
            return "break"
        valor = self.lista_autocomplete.get(selecao[0])
        self.var_nome.set(valor)
        self.combo_nome.icursor(tk.END)
        self.fechar_autocomplete()
        self.combo_nome.focus_set()
        return "break"

    def autocomplete_baixo(self, event=None):
        if not self.opcoes_visiveis or not self.lista_autocomplete: return "break"
        atual = self.lista_autocomplete.curselection()
        indice = atual[0] + 1 if atual else 0
        indice = min(indice, len(self.opcoes_visiveis) - 1)
        self.lista_autocomplete.selection_clear(0, tk.END)
        self.lista_autocomplete.selection_set(indice)
        self.lista_autocomplete.activate(indice)
        self.lista_autocomplete.see(indice)
        return "break"

    def autocomplete_cima(self, event=None):
        if not self.opcoes_visiveis or not self.lista_autocomplete: return "break"
        atual = self.lista_autocomplete.curselection()
        indice = atual[0] - 1 if atual else 0
        indice = max(indice, 0)
        self.lista_autocomplete.selection_clear(0, tk.END)
        self.lista_autocomplete.selection_set(indice)
        self.lista_autocomplete.activate(indice)
        self.lista_autocomplete.see(indice)
        return "break"

    def autocomplete_enter(self, event=None):
        if self.opcoes_visiveis and self.lista_autocomplete:
            self.selecionar_autocomplete()
            return "break"
        self.fechar_autocomplete()
        self.manter()
        return "break"

    def autocomplete_mouse_move(self, event):
        if not self.lista_autocomplete: return
        indice = self.lista_autocomplete.nearest(event.y)
        if 0 <= indice < len(self.opcoes_visiveis):
            self.lista_autocomplete.selection_clear(0, tk.END)
            self.lista_autocomplete.selection_set(indice)
            self.lista_autocomplete.activate(indice)

    def autocomplete_focus_out(self, event=None):
        self.root.after(150, self.verificar_foco_autocomplete)

    def verificar_foco_autocomplete(self):
        try:
            foco = self.root.focus_get()
            if foco not in (self.combo_nome, self.lista_autocomplete):
                self.fechar_autocomplete()
        except tk.TclError:
            self.fechar_autocomplete()

    def fechar_autocomplete(self, event=None):
        self.opcoes_visiveis = []
        if self.popup_autocomplete is not None:
            try:
                self.popup_autocomplete.destroy()
            except tk.TclError:
                pass
        self.popup_autocomplete = None
        self.lista_autocomplete = None
        if event is not None:
            return "break"

    def carregar_arquivos(self):
        extensoes = ('.png', '.jpg', '.jpeg')
        self.arquivos = []
        for raiz, _, files in os.walk(self.pasta_raiz):
            if "Lixeira" in raiz: continue
            for f in files:
                if f.lower().endswith(extensoes):
                    self.arquivos.append(os.path.join(raiz, f))
        
        if not self.arquivos:
            messagebox.showinfo("Tudo Limpo!", "Nenhum documento de imagem encontrado para verificar.")
            self.root.quit()
        else:
            self.root.update()
            self.mostrar_imagem()

    def mostrar_imagem(self):
        if self.indice_atual >= len(self.arquivos):
            messagebox.showinfo("Concluído", "Verificou todos os documentos!")
            self.root.quit()
            return

        caminho_completo = self.arquivos[self.indice_atual]
        if not os.path.exists(caminho_completo):
            self.canvas.delete("all")
            self.canvas.create_text(
                self.canvas.winfo_width()/2, self.canvas.winfo_height()/2, 
                text="Este ficheiro já foi movido ou eliminado.", font=("Arial", 14)
            )
            self.fechar_autocomplete()
            self.var_nome.set("FICHEIRO AUSENTE")
            self.lbl_extensao.config(text="")
            return

        pasta_atual, nome_arquivo = os.path.split(caminho_completo)
        nome_aluno = os.path.basename(pasta_atual)
        self.lbl_aluno.config(text=f"📁 Pasta: {nome_aluno}  |  Doc {self.indice_atual + 1} de {len(self.arquivos)}")
        nome_base, ext = os.path.splitext(nome_arquivo)
        self.var_nome.set(nome_base)
        self.extensao_atual = ext
        self.lbl_extensao.config(text=ext)
        self.fechar_autocomplete()
        self.combo_nome.focus()

        try:
            if self.img_original: 
                self.img_original.close()
            self.img_original = Image.open(caminho_completo)
            canvas_w = max(self.canvas.winfo_width(), 100)
            canvas_h = max(self.canvas.winfo_height(), 100)
            img_w, img_h = self.img_original.size
            self.escala = min(canvas_w / img_w, canvas_h / img_h)
            self.offset_x, self.offset_y = canvas_w / 2, canvas_h / 2
            self.atualizar_imagem()
        except Exception as e:
            self.canvas.delete("all")
            self.canvas.create_text(
                self.canvas.winfo_width()/2, self.canvas.winfo_height()/2, 
                text=f"Erro ao carregar:\n{e}", font=("Arial", 12)
            )

    def atualizar_imagem(self):
        if self.img_original:
            nova_largura = int(self.img_original.width * self.escala)
            nova_altura = int(self.img_original.height * self.escala)
            
            if nova_largura < 50 or nova_altura < 50 or nova_largura > 8000 or nova_altura > 8000: 
                return
                
            # Otimização com thumbnail (consome menos RAM que resize completo)[cite: 1, 2]
            img_redim = self.img_original.copy()
            img_redim.thumbnail((nova_largura, nova_altura), Image.Resampling.LANCZOS)
            
            self.img_tk = ImageTk.PhotoImage(img_redim)
            self.canvas.delete("all")
            self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.CENTER, image=self.img_tk)

    def zoom(self, event):
        if event.delta > 0 or event.num == 4: self.escala *= 1.15
        elif event.delta < 0 or event.num == 5: self.escala *= 0.85
        self.atualizar_imagem()

    def iniciar_arrasto(self, event):
        self.drag_data["x"], self.drag_data["y"] = event.x, event.y

    def arrastar(self, event):
        self.offset_x += event.x - self.drag_data["x"]
        self.offset_y += event.y - self.drag_data["y"]
        self.drag_data["x"], self.drag_data["y"] = event.x, event.y
        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.CENTER, image=self.img_tk)

    def rodar_imagem(self):
        caminho_completo = self.arquivos[self.indice_atual]
        if self.var_nome.get() == "FICHEIRO AUSENTE": return
        try:
            if self.img_original: self.img_original.close()
            with Image.open(caminho_completo) as img:
                img_rodada = img.rotate(-90, expand=True)
                img_rodada.save(caminho_completo)
            self.mostrar_imagem()
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao rodar a imagem:\n{e}")

    def voltar(self):
        if self.indice_atual > 0:
            self.indice_atual -= 1
            self.mostrar_imagem()
        else:
            messagebox.showinfo("Aviso", "Esta já é a primeira imagem.")

    def manter(self):
        caminho_antigo = self.arquivos[self.indice_atual]
        pasta_atual, nome_antigo = os.path.split(caminho_antigo)
        nome_antigo_base, _ = os.path.splitext(nome_antigo)
        nome_novo_base = self.var_nome.get().strip()

        if nome_novo_base == "" or nome_novo_base == "FICHEIRO AUSENTE" or nome_novo_base == nome_antigo_base:
            self.indice_atual += 1
            self.mostrar_imagem()
            return

        caminho_novo = gerar_caminho_unico(pasta_atual, nome_novo_base, self.extensao_atual)
        
        try:
            if self.img_original: self.img_original.close()
            os.rename(caminho_antigo, caminho_novo)
            self.arquivos[self.indice_atual] = caminho_novo
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao tentar renomear:\n{e}")
            return
        self.indice_atual += 1
        self.mostrar_imagem()

    def deletar(self):
        caminho_completo = self.arquivos[self.indice_atual]
        _, nome_arquivo = os.path.split(caminho_completo)
        if self.var_nome.get() == "FICHEIRO AUSENTE":
            self.indice_atual += 1
            self.mostrar_imagem()
            return
            
        pasta_lixeira = os.path.join(self.pasta_raiz, "Lixeira")
        if not os.path.exists(pasta_lixeira): 
            os.makedirs(pasta_lixeira)
            
        nome_sem_extensao, ext = os.path.splitext(nome_arquivo)
        caminho_lixeira = gerar_caminho_unico(pasta_lixeira, nome_sem_extensao, ext)

        if messagebox.askyesno("Confirmar Envio", f"Mover '{nome_arquivo}' para a Lixeira?"):
            try:
                if self.img_original: self.img_original.close()
                os.rename(caminho_completo, caminho_lixeira)
                self.arquivos[self.indice_atual] = caminho_lixeira
                self.indice_atual += 1
                self.mostrar_imagem()
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao mover para a Lixeira:\n{e}")


# ============================================================================
# CLASSE ARQUIVADOR EM LOTE
# ============================================================================
class ArquivadorLote:
    def __init__(self, root, pasta_raiz):
        self.root = root
        self.pasta_raiz = pasta_raiz
        self.root.title("Arquivador Automático em Lote")
        self.root.geometry("450x380")
        self.root.configure(bg="#f4f4f4")
        self.arquivos_selecionados = []
        self.pastas_alunos = self.mapear_pastas()

        self.lista_categorias = CATEGORIAS_DOCUMENTOS

        tk.Label(self.root, text="Arquivador Rápido por RM", font=("Arial", 14, "bold"), bg="#f4f4f4", fg="#2c3e50").pack(pady=15)

        tk.Label(self.root, text="1. Qual é o Documento? (Escolha ou Digite):", bg="#f4f4f4", font=("Arial", 10, "bold")).pack(pady=(10, 0))
        self.var_tipo = tk.StringVar()
        self.combo_tipo = ttk.Combobox(self.root, textvariable=self.var_tipo, values=self.lista_categorias, state="normal", font=("Arial", 11), width=40)
        self.combo_tipo.pack(pady=5)
        if self.lista_categorias:
            self.combo_tipo.current(0)

        tk.Label(self.root, text="2. Selecione os Arquivos (Os nomes devem ser o RM):", bg="#f4f4f4", font=("Arial", 10, "bold")).pack(pady=(20, 0))
        self.btn_selecionar = tk.Button(self.root, text="Selecionar Arquivos...", command=self.selecionar_arquivos, font=("Arial", 10, "bold"), bg="#f39c12", fg="white")
        self.btn_selecionar.pack(pady=5)
        
        self.lbl_arquivo = tk.Label(self.root, text="0 arquivo(s) selecionado(s)", bg="#f4f4f4", fg="#7f8c8d")
        self.lbl_arquivo.pack(pady=5)

        self.btn_arquivar = tk.Button(self.root, text="Mover e Renomear Tudo", command=self.arquivar, font=("Arial", 12, "bold"), bg="#2ecc71", fg="white", width=25)
        self.btn_arquivar.pack(pady=20)

    def mapear_pastas(self):
        """Mapeia as pastas criando um dicionário ultrarrápido (RM -> Caminho)[cite: 2]."""
        self.dicionario_rms = {}
        pastas_nomes = []
        
        for raiz, subdiretorios, _ in os.walk(self.pasta_raiz):
            subdiretorios[:] = [d for d in subdiretorios if d not in ["Lixeira", "Backups"] and not d.startswith('.')]
            for subpasta in subdiretorios:
                if subpasta and subpasta[0].isdigit():
                    caminho_completo = os.path.join(raiz, subpasta)
                    pastas_nomes.append(caminho_completo)
                    
                    rm_str = re.sub(r'\D', '', subpasta.split('-')[0])
                    if rm_str:
                        self.dicionario_rms[int(rm_str)] = caminho_completo
                        
        return pastas_nomes

    def selecionar_arquivos(self):
        caminhos = filedialog.askopenfilenames(
            title="Selecione os documentos", 
            filetypes=[("Imagens e PDFs", "*.jpg *.jpeg *.png *.pdf"), ("Todos os Arquivos", "*.*")]
        )
        if caminhos:
            self.arquivos_selecionados = caminhos
            self.lbl_arquivo.config(text=f"{len(caminhos)} arquivo(s) selecionado(s)", fg="#27ae60", font=("Arial", 10, "bold"))

    def arquivar(self):
        if not self.arquivos_selecionados:
            messagebox.showwarning("Aviso", "Selecione pelo menos um arquivo!")
            return

        tipo = self.var_tipo.get().strip()
        if not tipo:
            messagebox.showwarning("Aviso", "Escolha ou digite o tipo de documento!")
            return

        sucessos = 0
        erros = []

        for caminho_arquivo in self.arquivos_selecionados:
            nome_arquivo = os.path.basename(caminho_arquivo)
            rm_arquivo_str, ext = os.path.splitext(nome_arquivo)
            
            match_rm = re.search(r'\d+', rm_arquivo_str)
            
            if not match_rm:
                erros.append(f"{nome_arquivo} (Não tem números no nome)")
                continue
                
            rm_arquivo_clean = match_rm.group(0)
            rm_int_arquivo = int(rm_arquivo_clean)

            pasta_destino_completa = self.dicionario_rms.get(rm_int_arquivo)
            
            if not pasta_destino_completa:
                erros.append(f"{nome_arquivo} (Pasta com este RM não encontrada)")
                continue

            caminho_final = gerar_caminho_unico(pasta_destino_completa, tipo, ext)

            try:
                shutil.move(caminho_arquivo, caminho_final)
                sucessos += 1
            except Exception as e:
                erros.append(f"{nome_arquivo} (Erro no sistema: {e})")

        msg = f"Processo Concluído!\n\n✅ Sucessos: {sucessos} arquivo(s) arquivado(s)."
        if erros:
            msg += f"\n\n❌ Falhas ({len(erros)}):"
            for erro in erros[:5]:
                msg += f"\n- {erro}"
            if len(erros) > 5:
                msg += "\n... e outros."
            messagebox.showwarning("Aviso", msg)
        else:
            messagebox.showinfo("Sucesso", msg)

        self.arquivos_selecionados = []
        self.lbl_arquivo.config(text="0 arquivo(s) selecionado(s)", fg="#7f8c8d", font=("Arial", 10))


# ============================================================================
# MENU PRINCIPAL
# ============================================================================
def abrir_menu():
    menu = tk.Tk()
    menu.title("Sistema Híbrido de Triagem")
    menu.geometry("450x530")
    menu.configure(bg="#f4f4f4")

    verificar_atualizacoes()
    
    config_atual = carregar_configuracoes()

    tk.Label(menu, text="Gerenciador de Documentos", font=("Arial", 16, "bold"), bg="#f4f4f4", fg="#2c3e50").pack(pady=20)

    def btn_abrir_configuracoes():
        janela_config = tk.Toplevel(menu)
        janela_config.title("⚙️ Configurações de Pastas")
        janela_config.geometry("550x340")
        janela_config.configure(bg="#f4f4f4")
        janela_config.transient(menu)
        janela_config.grab_set()

        tk.Label(janela_config, text="Definir Diretórios do Sistema", font=("Arial", 14, "bold"), bg="#f4f4f4").pack(pady=15)

        tk.Label(janela_config, text="Pasta de Trabalho (Onde os arquivos chegam):", bg="#f4f4f4", font=("Arial", 9, "bold")).pack(anchor="w", padx=20)
        var_principal = tk.StringVar(value=config_atual["pasta_principal"])
        frame_p = tk.Frame(janela_config, bg="#f4f4f4")
        frame_p.pack(fill="x", padx=20, pady=2)
        tk.Entry(frame_p, textvariable=var_principal, width=42, font=("Arial", 10), state="readonly").pack(side="left")
        
        def escolher_principal():
            pasta = filedialog.askdirectory(title="Selecione a Pasta de Trabalho")
            if pasta: var_principal.set(pasta)
                
        tk.Button(frame_p, text="Procurar...", command=escolher_principal).pack(side="left", padx=10)

        tk.Label(janela_config, text="Pasta de Arquivo Final (Com os RMs):", bg="#f4f4f4", font=("Arial", 9, "bold")).pack(anchor="w", padx=20, pady=(10,0))
        var_destino = tk.StringVar(value=config_atual["pasta_destino_final"])
        frame_d = tk.Frame(janela_config, bg="#f4f4f4")
        frame_d.pack(fill="x", padx=20, pady=2)
        tk.Entry(frame_d, textvariable=var_destino, width=42, font=("Arial", 10), state="readonly").pack(side="left")

        def escolher_destino():
            pasta = filedialog.askdirectory(title="Selecione a Pasta Destino Final")
            if pasta: var_destino.set(pasta)

        tk.Button(frame_d, text="Procurar...", command=escolher_destino).pack(side="left", padx=10)

        tk.Label(janela_config, text="Chave da API do Gemini:", bg="#f4f4f4", font=("Arial", 9, "bold")).pack(anchor="w", padx=20, pady=(10, 0))
        var_api_key = tk.StringVar(value=config_atual.get("api_key_gemini", ""))
        entry_api = tk.Entry(janela_config, textvariable=var_api_key, width=55, font=("Arial", 10), show="*")
        entry_api.pack(padx=20, pady=2) 

        def salvar():
            config_atual["pasta_principal"] = var_principal.get()
            config_atual["pasta_destino_final"] = var_destino.get()
            config_atual["api_key_gemini"] = var_api_key.get().strip()
            salvar_configuracoes(config_atual)
            messagebox.showinfo("Sucesso", "Configurações salvas com sucesso!", parent=janela_config)
            janela_config.destroy()

        tk.Button(janela_config, text="💾 Salvar e Fechar", command=salvar, bg="#27ae60", fg="white", font=("Arial", 10, "bold"), width=20).pack(pady=15)

    def btn_rodar_nomeador():
        pasta = config_atual["pasta_principal"]
        chave = config_atual.get("api_key_gemini", "").strip()

        if not chave:
            messagebox.showwarning(
                "Aviso", 
                "Por favor, abra as '⚙️ Configurações de Pastas' e insira sua chave da API do Gemini antes de rodar o Nomeador!"
            )
            return

        btn_nomeador.config(state=tk.DISABLED, text="⏳ Processando...")
        menu.config(cursor="watch")

        # -- CRIA A JANELA DE PROGRESSO --
        janela_progresso = tk.Toplevel(menu)
        janela_progresso.title("Progresso do Nomeador")
        janela_progresso.geometry("400x180")
        janela_progresso.configure(bg="#f4f4f4")
        janela_progresso.transient(menu)
        janela_progresso.grab_set() # Bloqueia a janela de trás

        tk.Label(janela_progresso, text="Analisando documentos...", font=("Arial", 12, "bold"), bg="#f4f4f4", fg="#2c3e50").pack(pady=(15, 5))
        
        lbl_contador = tk.Label(janela_progresso, text="Mapeando arquivos na pasta...", font=("Arial", 10), bg="#f4f4f4")
        lbl_contador.pack(pady=5)

        barra_progresso = ttk.Progressbar(janela_progresso, orient="horizontal", length=300, mode="determinate")
        barra_progresso.pack(pady=10)
        
        lbl_arquivo_atual = tk.Label(janela_progresso, text="", font=("Arial", 8), bg="#f4f4f4", fg="#7f8c8d")
        lbl_arquivo_atual.pack()

        # Função que o nomeador vai chamar a cada arquivo para atualizar a tela
        def atualizar_ui(atual, total, nome_arquivo):
            def _atualizar():
                lbl_contador.config(text=f"{atual} de {total} arquivos foram nomeados")
                barra_progresso["maximum"] = total
                barra_progresso["value"] = atual
                lbl_arquivo_atual.config(text=f"Processando: {nome_arquivo}")
            # .after(0) garante que o Tkinter atualize a tela de forma segura a partir da thread de fundo
            menu.after(0, _atualizar)

        # -- EXECUÇÃO EM SEGUNDO PLANO --
        def tarefa_segundo_plano():
            erro_ocorrido = None
            try:
                # Passamos o atualizar_ui como callback_progresso
                nomeador.organizar_pasta(pasta, chave, callback_progresso=atualizar_ui)
            except Exception as e:
                erro_ocorrido = str(e)

            def finalizar_interface():
                menu.config(cursor="")
                btn_nomeador.config(state=tk.NORMAL, text="1. Iniciar Nomeador Automático (IA)")
                janela_progresso.destroy() # Fecha a janela de progresso
                
                if erro_ocorrido:
                    messagebox.showerror("Erro", f"Ocorreu um erro no nomeador:\n{erro_ocorrido}")
                else:
                    messagebox.showinfo("Concluído", "O Nomeador finalizou a triagem inteligente de todos os ficheiros!")

            menu.after(0, finalizar_interface)

        threading.Thread(target=tarefa_segundo_plano, daemon=True).start()

    def btn_abrir_verificador():
        menu.destroy() 
        root = tk.Tk() 
        AppVerificador(root, config_atual["pasta_principal"]) 
        root.mainloop()

    def btn_resetar():
        pasta = config_atual["pasta_principal"]
        resposta = messagebox.askyesno("Atenção!", f"Tem a certeza que deseja retirar os nomes atuais dos ficheiros de:\n{pasta}?")
        if resposta:
            menu.config(cursor="watch")
            menu.update()
            contador = 1
            extensoes_alvo = ('.png', '.jpg', '.jpeg', '.pdf')
            for raiz, _, arquivos in os.walk(pasta):
                if "Lixeira" in raiz: continue
                arquivos_compativeis = [f for f in arquivos if f.lower().endswith(extensoes_alvo)]
                for f in arquivos_compativeis:
                    caminho_antigo = os.path.join(raiz, f)
                    extensao = os.path.splitext(f)[1].lower()
                    novo_nome = f"teste ({contador}){extensao}"
                    caminho_novo = os.path.join(raiz, novo_nome)
                    while os.path.exists(caminho_novo):
                        if caminho_antigo == caminho_novo: break
                        contador += 1
                        novo_nome = f"teste ({contador}){extensao}"
                        caminho_novo = os.path.join(raiz, novo_nome)
                    if caminho_antigo != caminho_novo:
                        try: os.rename(caminho_antigo, caminho_novo)
                        except Exception: pass
                    contador += 1
            menu.config(cursor="")
            messagebox.showinfo("Sucesso", "Todos os ficheiros voltaram a ter nomes genéricos!")

    def abrir_manual():
        caminho_manual = os.path.join(os.path.dirname(__file__), "Manual_de_Uso.pdf")
        if os.path.exists(caminho_manual):
            webbrowser.open(caminho_manual)
        else:
            messagebox.showwarning("Aviso", "O arquivo do Manual não foi encontrado na pasta.")



    def btn_abrir_arquivador():
        janela = tk.Toplevel(menu)
        ArquivadorLote(janela, config_atual["pasta_destino_final"]) 

    # BOTÕES DO MENU
    btn_nomeador = tk.Button(
        menu, text="1. Iniciar Nomeador Automático (IA)", width=40, height=2, 
        bg="#3498db", fg="white", font=("Arial", 10, "bold"), command=btn_rodar_nomeador
    )
    btn_nomeador.pack(pady=7)
    
    tk.Button(
        menu, text="2. Abrir Verificador de Imagens", width=40, height=2, 
        bg="#2ecc71", fg="white", font=("Arial", 10, "bold"), command=btn_abrir_verificador
    ).pack(pady=7)
    
    tk.Button(
        menu, text="3. Repor Nomes Genéricos", width=40, height=2, 
        bg="#e74c3c", fg="white", font=("Arial", 10, "bold"), command=btn_resetar
    ).pack(pady=7)
    
    tk.Button(
        menu, text="4. Arquivador Automático (Por RM)", width=40, height=2, 
        bg="#f39c12", fg="white", font=("Arial", 10, "bold"), command=btn_abrir_arquivador
    ).pack(pady=7)

    # Botão no menu
    tk.Button(
        menu, text="📖 Manual (PDF)", width=40, height=1, 
        bg="#2980b9", fg="white", font=("Arial", 9, "bold"), command=abrir_manual
    ).pack(pady=5)
    
    tk.Button(
        menu, text="⚙️ Configurações de Pastas", width=40, height=1, 
        bg="#7f8c8d", fg="white", font=("Arial", 9, "bold"), command=btn_abrir_configuracoes
    ).pack(pady=15)

    menu.mainloop()

if __name__ == "__main__":
    abrir_menu()