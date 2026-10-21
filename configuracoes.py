import os
import json

ARQUIVO_CONFIG = "config_pastas.json"

CONFIG_PADRAO = {
    "pasta_principal": r"C:\Users\User\Pictures",
    "pasta_destino_final": r"D:\Docs Alunos",
    "api_key_gemini": ""
}

# Tupla imutável com os nomes de arquivos já processados (definida uma única vez em memória)
DOCUMENTOS_JA_CLASSIFICADOS = (
    "RG",
    "CNH", 
    "Hist. Escolar", 
    "Atestado", "Cert.", 
    "Matricula", 
    "Pedido", 
    "Declaração", 
    "Dec. de Escolaridade",
    "Dec. de Quitação",
    "Ficha", "Boletim", 
    "Advertência", 
    "Termo", 
    "Comp.", 
    "Guarda", 
    "Cartão", 
    "Relatório", 
    "Vazio", 
    "Nao_Identificado"
)

# Lista centralizada de categorias para evitar discrepâncias entre telas
CATEGORIAS_DOCUMENTOS = [
    "Atestado",
    "Advertência",
    "Boletim",
    "Cartão de Saúde",
    "Cert. de Óbito",
    "Cert. Nasc.",
    "Certificado de Conclusão",
    "CNH (mae)",
    "CNH (pai)",
    "Comp. de Res.",
    "Dec. de Escolaridade",
    "Dec. de Quitação",
    "Declaração de Transf.",
    "Ficha do Aluno",
    "Foto 3x4",
    "Guarda Parental",
    "Hist. Escolar",
    "Matricula",
    "Pedido de Transf.",
    "Relatório Pedagógico",
    "RG (aluno)",
    "RG (mae)",
    "RG (pai)",
    "Termo de Uso de Imagem"
]

def carregar_configuracoes():
    """Carrega as configurações do JSON ou retorna o dicionário padrão[cite: 2]."""
    if os.path.exists(ARQUIVO_CONFIG):
        try:
            with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
                dados = json.load(f)
                config = CONFIG_PADRAO.copy()
                config.update(dados)
                return config
        except Exception:
            return CONFIG_PADRAO.copy()
    return CONFIG_PADRAO.copy()

def salvar_configuracoes(config):
    """Salva o dicionário de configurações no arquivo JSON[cite: 2]."""
    with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def gerar_caminho_unico(pasta_destino, nome_base, extensao):
    """
    Gera um caminho de arquivo único para evitar colisões e sobrescritas acidentais[cite: 1].
    Exemplo: 'Atestado.pdf' -> 'Atestado (1).pdf' -> 'Atestado (2).pdf'[cite: 2, 3]
    """
    novo_nome = f"{nome_base}{extensao}"
    caminho_final = os.path.join(pasta_destino, novo_nome)
    contador = 1
    
    while os.path.exists(caminho_final):
        novo_nome = f"{nome_base} ({contador}){extensao}"
        caminho_final = os.path.join(pasta_destino, novo_nome)
        contador += 1
        
    return caminho_final