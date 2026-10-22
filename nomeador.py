import os
import time
import re
import unicodedata
import pytesseract
from PIL import Image
import pypdf
from google import genai
import sys

from configuracoes import DOCUMENTOS_JA_CLASSIFICADOS, gerar_caminho_unico

# ---------------------------------------------------------------------------
# CONFIGURAÇÕES DA MÁQUINA
# ---------------------------------------------------------------------------


# Identifica a pasta onde o executável (.exe) ou o script Python está rodando
if getattr(sys, 'frozen', False):
    pasta_execucao = os.path.dirname(sys.executable)
else:
    pasta_execucao = os.path.dirname(os.path.abspath(__file__))

# Tenta usar a pasta "Tesseract-OCR" local
tesseract_local = os.path.join(pasta_execucao, "Tesseract-OCR", "tesseract.exe")

if os.path.exists(tesseract_local):
    pytesseract.pytesseract.tesseract_cmd = tesseract_local
else:
    # Fallback para o caminho padrão de instalação do Windows
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

EXTENSOES_SUPORTADAS = ('.png', '.jpg', '.jpeg', '.pdf')

PROMPT_IA = """
Analise este documento de identidade (RG ou CNH).
Sua tarefa é identificar a quem ele pertence, analisando a data de nascimento, os nomes e a foto.
REGRAS:
1. Se a pessoa nasceu no ano 2000 ou depois, é o aluno. Retorne exatamente: "RG (aluno)".
2. Se a pessoa for mais velha (geralmente antes de 2000), deduza pelo nome, gênero e filiação se é o pai ou a mãe.
3. Retorne exatamente: "RG (pai)", "RG (mae)", "CNH (pai)" ou "CNH (mae)".
4. Caso não reconheça o documento pode analisar e nomear de acordo com o conteudo.

Responda APENAS com a string do nome final, sem aspas.
"""

# ---------------------------------------------------------------------------
# REGEX PRÉ-COMPILADOS NA MEMÓRIA
# ---------------------------------------------------------------------------
REGEX_ESPACOS = re.compile(r'\s+')
REGEX_CID = re.compile(r'\bcid\b')
REGEX_CRM = re.compile(r'\bcrm\b')
REGEX_ANOS = re.compile(r'\b20\d{2}\b')

# ---------------------------------------------------------------------------
# FUNÇÕES OFFLINE (TESSERACT)
# ---------------------------------------------------------------------------
def remover_acentos(texto):
    try:
        return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()
    except Exception:
        return texto.lower()

def extrair_texto_offline(caminho_arquivo):
    ext = os.path.splitext(caminho_arquivo)[1].lower()
    texto = ""
    try:
        if ext in ('.jpg', '.jpeg', '.png'):
            with Image.open(caminho_arquivo) as imagem:
                texto = pytesseract.image_to_string(imagem, lang='por')
        elif ext == '.pdf':
            # 1. Tenta extração direta do texto contido no PDF
            try:
                leitor = pypdf.PdfReader(caminho_arquivo)
                for pagina in leitor.pages:
                    texto_extraido = pagina.extract_text()
                    if texto_extraido:
                        texto += texto_extraido + " "
            except Exception:
                pass

            # 2. Fallback com OCR caso o PDF seja digitalizado como imagem[cite: 1, 3]
            if not texto.strip():
                try:
                    import pdf2image
                    paginas = pdf2image.convert_from_path(caminho_arquivo, first_page=1, last_page=3)
                    for pag in paginas:
                        texto += pytesseract.image_to_string(pag, lang='por') + " "
                except Exception:
                    pass

        return remover_acentos(texto)
    except Exception as e:
        print(f"      [!] Erro na leitura offline: {e}")
        return ""

def descobrir_curso(texto):
    """Mini-função para deduzir o grau escolar baseado na contagem de palavras."""
    if "prosseguimento no ensino medio" in texto or "concluiu o 9" in texto:
        return " - Ens. Fund."
    
    votos_fund = texto.count("ensino fundamental")
    votos_medio = texto.count("ensino medio")
    
    if votos_fund > votos_medio: return " - Ens. Fund."
    elif votos_medio > votos_fund: return " - Ens. Médio"
    return ""

def triagem_rapida(texto):
    """Filtra os documentos simples e aciona a IA para os complexos."""
    if len(texto.strip()) < 5:
        return "Documento_Vazio"

    texto = texto.replace('\n', ' ')
    texto = REGEX_ESPACOS.sub(' ', texto)

    # 1. IDENTIDADE E CNH
    if "carteira de identidade" in texto or "registro geral" in texto or "secretaria de seguranca" in texto or "nao plastificar" in texto or "polegar direito" in texto or "territorio nacional" in texto:
        return "ACIONAR_IA"
    if "carteira nacional de habilitacao" in texto or "detran" in texto or "permissao para dirigir" in texto or "ministerio da infraestrutura" in texto:
        return "ACIONAR_IA"

    # 2. BOLETIM ESCOLAR 
    if ("boletim" in texto or "assiduidade" in texto or "boletim escolar" in texto or 
        "bimestre" in texto or "apto a cursar" in texto or "componente curricular" in texto or 
        "total faltas" in texto or "aulas dadas" in texto or "c. final" in texto or 
        ("resultado final" in texto and ("recuperacao" in texto or "codigo" in texto))):
        
        if "transferencia durante o periodo letivo" not in texto and "historico escolar" not in texto:
            return "Boletim"

    # 3. CARTÃO DE SAÚDE 
    if ("cartao de saude" in texto or "cartao de saude da crianca" in texto or "saude da crianca" in texto or 
        "vacine-o" in texto or "servico de saude" in texto or "vacinacao" in texto or 
        "vacinas" in texto or "imunizacoes" in texto or "carteira de vacinacoes" in texto):
        return "Carteirinha de vacinação"

    # 4. FICHA DO ALUNO 
    if ("ficha individual" in texto or "ficha de matricula" in texto or "identificacao e medica" in texto or 
        "pediatra" in texto or "doencas infantis" in texto or 
        "sarampo" in texto or "catapora" in texto or "nome da crianca" in texto):
        return "Ficha do Aluno"

    # 5. CERTIDÃO DE ÓBITO
    if "certidao de obito" in texto or "causa da morte" in texto or "atestado de obito" in texto:
        return "Cert. de Óbito"

    # 6. ATESTADOS E COMPARECIMENTO
    if (("atestado" in texto and "transferencia" not in texto) or 
        "declaracao de falta" in texto or 
        "declaracao de comparecimento" in texto or 
        "paciente" in texto or "motivo de doenca" in texto or 
        "nao pode comparecer" in texto or "atividades habituais" in texto or 
        REGEX_CID.search(texto) or REGEX_CRM.search(texto)):
        return "Atestado"

    # 7. MATRÍCULA E ADESÃO
    if ("termo de adesao" in texto or "contrato de prestacao" in texto or 
        "requerimento de matricula" in texto or "tabela de valores" in texto or 
        "clausula" in texto or "contratante" in texto):
        anos = REGEX_ANOS.findall(texto)
        if anos:
            ano_contrato = max(anos) 
            return f"Matricula {ano_contrato}"
        return "Matricula"

    # 8. HISTÓRICO ESCOLAR
    if "historico escolar" in texto or "componentes curriculares" in texto or "transferencia durante o periodo letivo" in texto:
        curso = descobrir_curso(texto) 
        escola = " (Colégio Recanto Educacional)" if "recanto educacional" in texto else ""
        return f"Hist. Escolar{curso}{escola}"

    # 9. CERTIFICADO DE CONCLUSÃO
    if "certificado de conclusao" in texto or "certificacao" in texto:
        curso = descobrir_curso(texto) 
        escola = " (Colégio Recanto Educacional)" if "recanto educacional" in texto else ""
        return f"Certificado de Conclusão{curso}{escola}"
    
    # 10. TRANSFERÊNCIAS 
    if "atestado de transferencia" in texto or ("certifico" in texto and "transferencia" in texto):
        return "Declaração de Transf."
    elif "pedido de transferencia" in texto:
        return "Pedido de Transf."
    elif ("declaracao" in texto or "declaro para os devidos fins" in texto or "declara que" in texto) and "transferencia" in texto:
        return "Declaração de Transf."
    elif "transferencia" in texto and ("solicitar" in texto or "solicitou" in texto or "vaga" in texto or "unidade escolar" in texto):
        return "Pedido de Transf."

    # 11. CERTIDÃO DE NASCIMENTO
    if "certidao de nascimento" in texto or "registro civil" in texto or "republica federativa" in texto or "pessoas naturais" in texto or "oficial de registro" in texto or ("nascimento" in texto and "livro" in texto):
        return "Cert. de Nasc."

    # 12. TERMO DE USO DE IMAGEM
    if "termo de autorizacao" in texto or "uso de imagem" in texto or "protecao de dados" in texto:
        return "Termo de Uso de Imagem"

    # 13. COMPROVANTE DE RESIDÊNCIA
    if "comprovante de residencia" in texto or "fatura" in texto or "sabesp" in texto or "cpfl" in texto:
        return "Comp. de Res."

    # 14. ADVERTÊNCIA ESCOLAR
    if "advertencia" in texto or "adivertido" in texto or "registro de ocorrencia" in texto or "comunicado de ocorrencia" in texto or "indisciplina" in texto or "adverti" in texto or "advertido(a)" in texto:
        return "Advertência"
    
    # 15. GUARDA PARENTAL
    if "vara da infancia e da juventude" in texto or "guardiao(oes)" in texto or "guardiao" in texto or "guarda" in texto or "guarda parental" in texto:
        return "Guarda Parental"

    # 16. DECLARAÇÃO DE ESCOLARIDADE
    if "declaracao de escolaridade" in texto or ("declaro" in texto and "estudou" in texto):
        return "Dec. de Escolaridade"

    # 17. RELATÓRIO PEDAGÓGICO
    if "desempenho do aluno" in texto or "plantao pedagogico" in texto or "reuniao de pais" in texto or "apreciacao sobre o rendimento do aluno" in texto or "rendimento do aluno" in texto:
        return "Relatório Pedagógico"

    # 18. DECLARAÇÃO DE QUITAÇÃO
    if "declaracao de pagamento" in texto or "declaracao de quitacao" in texto:
        return "Dec. de Quitação"
    
    return "Documento_Nao_Identificado"

# ---------------------------------------------------------------------------
# FUNÇÃO ONLINE (GEMINI API)
# ---------------------------------------------------------------------------
def analisar_com_ia(caminho_arquivo, client):
    """Envia documentos de identidade para a IA com limpeza garantida no bloco finally[cite: 1, 3]."""
    print("      [+] Documento de identidade detectado! Acionando a IA...")
    tentativas = 0
    
    while tentativas < 3:
        arquivo_upload = None
        try:
            arquivo_upload = client.files.upload(file=caminho_arquivo)
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=[arquivo_upload, PROMPT_IA]
            )
            
            resultado = (response.text or "").strip()
            resultado_limpo = "".join(
                c for c in resultado 
                if c.isalnum() or c in (' ', '(', ')', '-')
            ).strip()
            
            return resultado_limpo if resultado_limpo else "Documento_Nao_Identificado"

        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print("      [!] Limite da API. Pausando 50s...")
                time.sleep(50)
                tentativas += 1
            else:
                print(f"      [!] Erro na IA: {e}")
                return "Erro_Processamento"
        finally:
            # Exclusão garantida do arquivo temporário enviado à nuvem[cite: 1, 3]
            if arquivo_upload is not None:
                try:
                    client.files.delete(name=arquivo_upload.name)
                except Exception as e:
                    print(f"      [!] Aviso ao excluir temporário na nuvem: {e}")
                
    return "Erro_Processamento"

# ---------------------------------------------------------------------------
# MOTOR PRINCIPAL (Substitua a função organizar_pasta por esta)
# ---------------------------------------------------------------------------
def organizar_pasta(caminho_pasta, api_key, callback_progresso=None):
    client = genai.Client(api_key=api_key)
    
    if not os.path.exists(caminho_pasta):
        print("Erro: Pasta não encontrada.")
        return

    print("\nIniciando sistema HÍBRIDO (Tesseract + Gemini)...\n")

    # 1. Pré-mapeamento: Conta e lista apenas os arquivos que precisam ser processados
    arquivos_para_processar = []
    for raiz, _, arquivos in os.walk(caminho_pasta):
        for nome_arquivo in arquivos:
            if nome_arquivo.lower().endswith(EXTENSOES_SUPORTADAS):
                # Se o arquivo não contiver uma categoria já classificada, adiciona à fila
                if not any(categoria in nome_arquivo for categoria in DOCUMENTOS_JA_CLASSIFICADOS):
                    arquivos_para_processar.append((raiz, nome_arquivo))

    total_arquivos = len(arquivos_para_processar)

    # 2. Processamento da lista com envio de progresso
    for atual, (raiz, nome_arquivo) in enumerate(arquivos_para_processar, start=1):
        
        # Envia a contagem atual para a interface (se a interface estiver escutando)
        if callback_progresso:
            callback_progresso(atual, total_arquivos, nome_arquivo)
            
        caminho_antigo = os.path.join(raiz, nome_arquivo)
        print(f"Analisando: {nome_arquivo} ...")
        
        texto = extrair_texto_offline(caminho_antigo)
        categoria = triagem_rapida(texto)
        
        if categoria == "ACIONAR_IA":
            categoria = analisar_com_ia(caminho_antigo, client)
            if categoria == "Erro_Processamento":
                continue

        extensao = os.path.splitext(nome_arquivo)[1].lower()
        caminho_novo = gerar_caminho_unico(raiz, categoria, extensao)

        try:
            os.rename(caminho_antigo, caminho_novo)
            print(f"   --> Renomeado para: {os.path.basename(caminho_novo)}\n")
        except Exception as e:
            print(f"   --> Erro ao renomear: {e}\n")

if __name__ == "__main__":
    print("Por favor, rode o script através da interface.py!")