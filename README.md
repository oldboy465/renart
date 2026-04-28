# 📖 Renomeador de Artigos Científicos - IA Gemini 2.5

![Python](https://img.shields.io/badge/python-3.12-blue.svg)
![PyQt5](https://img.shields.io/badge/PyQt5-GUI-green.svg)
![Gemini](https://img.shields.io/badge/AI-Gemini_2.5_Flash-orange.svg)

Uma ferramenta de desktop desenvolvida para facilitar a vida de pesquisadores e acadêmicos. O programa automatiza a renomeação de arquivos PDF científicos utilizando Inteligência Artificial para extrair metadados diretamente da primeira página do artigo.

A interface foi projetada com a estética **Frutiger Aero**, trazendo de volta o visual vibrante e "glossy" que marcou a era do Windows Vista/7.

## ✨ Funcionalidades

- **Extração Inteligente**: Utiliza o modelo Gemini 2.5 Flash para identificar o sobrenome do primeiro autor e o ano de publicação.
- **Padronização Automática**: Renomeia arquivos para o formato `Sobrenome - Ano.pdf`.
- **Interface Gráfica (GUI)**: Desenvolvida em PyQt5 com efeitos de transparência e brilho.
- **Segurança de Cota**: Sistema de delay automático (5s) e pausa longa (60s) para respeitar os limites do plano gratuito do Google AI Studio.
- **Persistência de Dados**: Salva sua última Chave API utilizada localmente para facilitar o uso recorrente.

## 🚀 Como usar

1. **Obtenha sua Chave API**:
   - Acesse o [Google AI Studio](https://aistudio.google.com/).
   - Gere uma nova chave no menu "Get API Key".
2. **Execute o Programa**:
   - Insira sua chave no campo correspondente.
   - Selecione a pasta contendo seus PDFs.
   - Clique em "Iniciar Processamento".

## 🛠️ Requisitos Técnicos

- Python 3.x
- Bibliotecas necessárias:
  - `PyQt5` (Interface Gráfica)
  - `PyMuPDF` (Manipulação de PDFs)
  - `requests` (Comunicação com a API)

```bash
pip install PyQt5 pymupdf requests