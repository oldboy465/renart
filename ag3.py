import os
import time
import re
import fitz  # PyMuPDF
import requests
import json
import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QTextEdit, 
                             QFileDialog, QMessageBox, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont

CONFIG_FILE = "config_api.json"

class RenomeadorThread(QThread):
    """Thread separada para não congelar a interface gráfica durante o processamento"""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, api_key, pasta_artigos):
        super().__init__()
        self.api_key = api_key
        self.pasta_artigos = pasta_artigos
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"
        self.rodando = True

    def extrair_metadados_ia(self, texto_pagina):
        payload = {
            "contents": [{
                "parts": [{
                    "text": (
                        "Analise o texto e retorne APENAS: Sobrenome do primeiro autor - Ano. "
                        "Exemplo: Silva - 2023. Não escreva mais nada. "
                        f"\n\nTexto: {texto_pagina}"
                    )
                }]
            }]
        }
        headers = {'Content-Type': 'application/json'}

        try:
            response = requests.post(self.url, headers=headers, data=json.dumps(payload))
            res_json = response.json()
            
            if response.status_code == 200:
                resultado = res_json['candidates'][0]['content']['parts'][0]['text']
                return resultado.strip()
            elif response.status_code == 429:
                self.log_signal.emit("--- Cota atingida. Aguardando 60s... ---")
                time.sleep(60)
                return self.extrair_metadados_ia(texto_pagina)
            else:
                self.log_signal.emit(f"Erro na API ({response.status_code}): {res_json}")
                return None
                
        except Exception as e:
            self.log_signal.emit(f"Erro de conexão: {e}")
            return None

    def run(self):
        arquivos = [f for f in os.listdir(self.pasta_artigos) if f.lower().endswith(".pdf")]
        total = len(arquivos)
        
        if total == 0:
            self.log_signal.emit("Nenhum PDF encontrado na pasta selecionada.")
            self.finished_signal.emit()
            return

        self.log_signal.emit(f"Iniciando processamento de {total} arquivos...")

        for i, arquivo in enumerate(arquivos):
            if not self.rodando:
                self.log_signal.emit("Processo cancelado pelo usuário.")
                break

            caminho_antigo = os.path.join(self.pasta_artigos, arquivo)
            
            if re.search(r" - \d{4}", arquivo):
                self.log_signal.emit(f"[{i+1}/{total}] Ignorando (já formatado): {arquivo}")
                continue

            try:
                doc = fitz.open(caminho_antigo)
                texto = doc[0].get_text()[:1500] 
                doc.close()

                self.log_signal.emit(f"[{i+1}/{total}] Analisando: {arquivo}")
                info = self.extrair_metadados_ia(texto)
                
                if info:
                    nome_limpo = re.sub(r'[\n\r\t]', " ", info)
                    nome_limpo = re.sub(r'[\\/*?:"<>|]', "", nome_limpo).strip()
                    
                    if "-" in nome_limpo and len(nome_limpo) > 4:
                        novo_nome = f"{nome_limpo}.pdf"
                        caminho_novo = os.path.join(self.pasta_artigos, novo_nome)

                        if not os.path.exists(caminho_novo):
                            os.rename(caminho_antigo, caminho_novo)
                            self.log_signal.emit(f"   ✓ Sucesso: {novo_nome}")
                        else:
                            self.log_signal.emit(f"   ! Nome já existe: {novo_nome}")
                    else:
                        self.log_signal.emit(f"   ? Resposta estranha da IA: {info}")
                
                time.sleep(5)

            except Exception as e:
                self.log_signal.emit(f"   X Erro ao processar {arquivo}: {e}")

        self.log_signal.emit("\nProcessamento concluído!")
        self.finished_signal.emit()

    def stop(self):
        self.rodando = False


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Renomeador de Artigos com IA")
        self.resize(700, 550)
        self.thread = None
        self.setup_ui()
        self.carregar_config()

    def setup_ui(self):
        # Cabeçalho (Título + Botão Ajuda)
        header_layout = QHBoxLayout()
        lbl_titulo = QLabel("Renomeador de Artigos Científicos")
        lbl_titulo.setStyleSheet("font-size: 20px; font-weight: bold; color: #0C4A6E;") # Removido o text-shadow
        
        # Criando a sombra no texto do jeito correto no PyQt5
        sombra_texto = QGraphicsDropShadowEffect()
        sombra_texto.setBlurRadius(2)
        sombra_texto.setColor(QColor(255, 255, 255, 200)) # Sombra branca
        sombra_texto.setOffset(1, 1)
        lbl_titulo.setGraphicsEffect(sombra_texto)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Container Aero Glass
        self.glass_panel = QWidget()
        self.glass_panel.setObjectName("glassPanel")
        glass_layout = QVBoxLayout(self.glass_panel)
        glass_layout.setSpacing(12)
        
        # Sombra suave para o painel
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 4)
        self.glass_panel.setGraphicsEffect(shadow)

        # Cabeçalho (Título + Botão Ajuda)
        header_layout = QHBoxLayout()
        lbl_titulo = QLabel("Renomeador de Artigos Científicos")
        lbl_titulo.setStyleSheet("font-size: 20px; font-weight: bold; color: #0C4A6E; text-shadow: 1px 1px 2px #FFFFFF;")
        
        self.btn_ajuda = QPushButton("❓ Ajuda")
        self.btn_ajuda.setToolTip("Clique para ver instruções de uso e como obter sua chave API.")
        self.btn_ajuda.clicked.connect(self.mostrar_ajuda)
        
        header_layout.addWidget(lbl_titulo)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_ajuda)
        glass_layout.addLayout(header_layout)

        # Linha separadora
        linha = QWidget()
        linha.setFixedHeight(1)
        linha.setStyleSheet("background-color: #A1C6E7;")
        glass_layout.addWidget(linha)

        # API KEY
        layout_api = QHBoxLayout()
        lbl_api = QLabel("Chave API:")
        lbl_api.setFixedWidth(80)
        self.input_api = QLineEdit()
        self.input_api.setEchoMode(QLineEdit.Password)
        self.input_api.setPlaceholderText("Cole aqui a sua chave do Google AI Studio...")
        layout_api.addWidget(lbl_api)
        layout_api.addWidget(self.input_api)
        glass_layout.addLayout(layout_api)

        # Pasta
        layout_pasta = QHBoxLayout()
        lbl_pasta = QLabel("Pasta (PDFs):")
        lbl_pasta.setFixedWidth(80)
        self.input_pasta = QLineEdit()
        self.input_pasta.setPlaceholderText("Caminho da pasta dos artigos...")
        self.btn_procurar = QPushButton("Procurar...")
        self.btn_procurar.clicked.connect(self.selecionar_pasta)
        layout_pasta.addWidget(lbl_pasta)
        layout_pasta.addWidget(self.input_pasta)
        layout_pasta.addWidget(self.btn_procurar)
        glass_layout.addLayout(layout_pasta)

        # Botão Iniciar
        self.btn_iniciar = QPushButton("Iniciar Processamento")
        self.btn_iniciar.setObjectName("btnIniciar") # Para aplicar o estilo verde Frutiger
        self.btn_iniciar.clicked.connect(self.iniciar_processo)
        glass_layout.addWidget(self.btn_iniciar)

        # Log
        lbl_log = QLabel("Registro de Atividades:")
        lbl_log.setStyleSheet("font-weight: bold; color: #334155; margin-top: 5px;")
        glass_layout.addWidget(lbl_log)
        
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        glass_layout.addWidget(self.txt_log)

        # Autoria
        lbl_autoria = QLabel("Desenvolvido por Philipe - github @oldboy465")
        lbl_autoria.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl_autoria.setStyleSheet("font-size: 11px; color: #475569; font-style: italic;")
        glass_layout.addWidget(lbl_autoria)

        main_layout.addWidget(self.glass_panel)

    def carregar_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    dados = json.load(f)
                    chave_salva = dados.get("api_key", "")
                    
                    if chave_salva:
                        # Pergunta se quer usar a última chave
                        resposta = QMessageBox.question(
                            self, 'Chave Encontrada', 
                            'Foi encontrada uma Chave API salva anteriormente.\nDeseja utilizá-la?',
                            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                        )
                        
                        if resposta == QMessageBox.Yes:
                            self.input_api.setText(chave_salva)
            except Exception as e:
                print(f"Erro ao ler config: {e}")

    def salvar_config(self, chave):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"api_key": chave}, f)
        except Exception as e:
            print(f"Erro ao salvar config: {e}")

    def selecionar_pasta(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecione a pasta com os PDFs")
        if pasta:
            # Converte as barras para o padrão do SO
            self.input_pasta.setText(os.path.normpath(pasta))

    def log(self, mensagem):
        self.txt_log.append(mensagem)
        # Rola o log para baixo automaticamente
        scrollbar = self.txt_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def mostrar_ajuda(self):
        texto_ajuda = (
            "<h3>Como utilizar o Renomeador de Artigos</h3>"
            "<p>Este programa lê a primeira página de cada arquivo PDF da pasta selecionada, envia para a Inteligência Artificial e renomeia o arquivo automaticamente para o padrão <b>Sobrenome - Ano.pdf</b>.</p>"
            "<hr>"
            "<h4>🔑 Como obter a Chave API:</h4>"
            "<ol>"
            "<li>Acesse o site: <b>aistudio.google.com</b></li>"
            "<li>Faça login com sua conta Google.</li>"
            "<li>No menu lateral esquerdo, clique em <b>Get API key</b>.</li>"
            "<li>Clique no botão azul <b>Create API key</b> e gere uma chave.</li>"
            "<li>Copie o código gerado e cole no campo 'Chave API' do programa.</li>"
            "</ol>"
            "<hr>"
            "<h4>🧠 Sobre o Modelo:</h4>"
            "<p>O programa utiliza exclusivamente o modelo <b>Gemini 2.5 Flash</b> via API REST nativa. Ele é extremamente rápido e otimizado para extração de dados em textos longos, ideal para artigos científicos.</p>"
            "<hr>"
            "<h4>⚠️ Orientações Gerais:</h4>"
            "<ul>"
            "<li>O plano gratuito do Google permite até <b>15 solicitações por minuto</b>. O programa já pausa automaticamente 5 segundos entre cada arquivo para evitar bloqueios.</li>"
            "<li>Arquivos que já estão no formato correto (ex: <i>Silva - 2024.pdf</i>) serão pulados para economizar o seu limite diário.</li>"
            "<li>Não se preocupe em minimizar o aplicativo, o processo continuará em segundo plano graças ao uso de threads.</li>"
            "</ul>"
        )
        
        caixa_ajuda = QMessageBox(self)
        caixa_ajuda.setWindowTitle("Ajuda e Orientações")
        caixa_ajuda.setIcon(QMessageBox.Information)
        caixa_ajuda.setTextFormat(Qt.RichText)
        caixa_ajuda.setText(texto_ajuda)
        caixa_ajuda.setStandardButtons(QMessageBox.Ok)
        caixa_ajuda.exec_()

    def iniciar_processo(self):
        api_key = self.input_api.text().strip()
        pasta = self.input_pasta.text().strip()

        if not api_key:
            QMessageBox.warning(self, "Aviso", "Por favor, insira a sua Chave API.")
            return
            
        if not pasta or not os.path.exists(pasta):
            QMessageBox.warning(self, "Aviso", "Por favor, selecione uma pasta válida.")
            return

        # Salva a chave para a próxima execução
        self.salvar_config(api_key)

        # Prepara a interface
        self.btn_iniciar.setEnabled(False)
        self.btn_iniciar.setText("Processando... Aguarde a finalização")
        self.input_api.setEnabled(False)
        self.input_pasta.setEnabled(False)
        self.btn_procurar.setEnabled(False)
        self.txt_log.clear()

        # Inicia a Thread
        self.thread = RenomeadorThread(api_key, pasta)
        self.thread.log_signal.connect(self.log)
        self.thread.finished_signal.connect(self.processo_finalizado)
        self.thread.start()

    def processo_finalizado(self):
        self.btn_iniciar.setEnabled(True)
        self.btn_iniciar.setText("Iniciar Processamento")
        self.input_api.setEnabled(True)
        self.input_pasta.setEnabled(True)
        self.btn_procurar.setEnabled(True)
        QMessageBox.information(self, "Concluído", "O processamento de todos os arquivos foi finalizado!")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Força estilo global padrão limpo para o QSS funcionar perfeitamente
    app.setStyle("Fusion") 
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())