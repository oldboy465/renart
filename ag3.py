import os
import time
import re
import fitz  # PyMuPDF
import requests
import json
import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QTextEdit, 
                             QFileDialog, QMessageBox, QGraphicsDropShadowEffect,
                             QComboBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor

CONFIG_FILE = "config_api.json"

class RenomeadorThread(QThread):
    """Thread separada para não congelar a interface gráfica durante o processamento"""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, provider, api_key, model, pasta_artigos):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.pasta_artigos = pasta_artigos
        self.rodando = True

    def extrair_metadados_ia(self, texto_pagina):
        prompt = (
            "Você é um assistente especializado em biblioteconomia. "
            "Analise o cabeçalho/topo da primeira página deste artigo científico e extraia os dados principais.\n"
            "Retorne APENAS no formato: Sobrenome do primeiro autor - Ano de publicação.\n"
            "Exemplo: Silva - 2023\n"
            "ATENÇÃO: Foque no ano de PUBLICAÇÃO do artigo. Ignore completamente anos de citações bibliográficas no meio do texto, "
            "datas de 'recebido em' ou 'aceito em'. Não escreva absolutamente mais nada, nem ponto final.\n\n"
            f"Texto extraído do topo da página:\n{texto_pagina}"
        )

        try:
            if self.provider == "Google AI Studio":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                headers = {'Content-Type': 'application/json'}
                
                response = requests.post(url, headers=headers, data=json.dumps(payload))
                res_json = response.json()
                
                if response.status_code == 200:
                    resultado = res_json['candidates'][0]['content']['parts'][0]['text']
                    return resultado.strip()
                elif response.status_code == 429:
                    self.log_signal.emit("--- Cota atingida. Aguardando 60s... ---")
                    time.sleep(60)
                    return self.extrair_metadados_ia(texto_pagina)
                else:
                    self.log_signal.emit(f"Erro na API Google ({response.status_code}): {res_json}")
                    return None

            elif self.provider == "OpenRouter":
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/oldboy465", 
                    "X-Title": "Renomeador de Artigos"
                }
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100  # CORREÇÃO DO ERRO 402: Limita a reserva de tokens na conta
                }

                response = requests.post(url, headers=headers, data=json.dumps(payload))
                res_json = response.json()

                if response.status_code == 200:
                    resultado = res_json['choices'][0]['message']['content']
                    return resultado.strip()
                elif response.status_code == 429:
                    self.log_signal.emit("--- Limite de requisições OpenRouter atingido. Aguardando 30s... ---")
                    time.sleep(30)
                    return self.extrair_metadados_ia(texto_pagina)
                else:
                    self.log_signal.emit(f"Erro na API OpenRouter ({response.status_code}): {res_json}")
                    return None

        except Exception as e:
            self.log_signal.emit(f"Erro de conexão/processamento: {e}")
            return None

    def run(self):
        arquivos = [f for f in os.listdir(self.pasta_artigos) if f.lower().endswith(".pdf")]
        total = len(arquivos)
        
        if total == 0:
            self.log_signal.emit("Nenhum arquivo PDF encontrado na pasta selecionada.")
            self.finished_signal.emit()
            return

        # Ajuste no log para mostrar qual modelo está sendo usado no OpenRouter
        if self.provider == "OpenRouter":
            self.log_signal.emit(f"Iniciando processamento de {total} arquivos via {self.provider} ({self.model})...")
        else:
            self.log_signal.emit(f"Iniciando processamento de {total} arquivos via {self.provider}...")

        for i, arquivo in enumerate(arquivos):
            if not self.rodando:
                self.log_signal.emit("Processo cancelado pelo usuário.")
                break

            caminho_antigo = os.path.join(self.pasta_artigos, arquivo)
            
            # Pula arquivos que já parecem estar formatados
            if re.search(r" - \d{4}", arquivo):
                self.log_signal.emit(f"[{i+1}/{total}] Ignorando (já formatado): {arquivo}")
                continue

            try:
                doc = fitz.open(caminho_antigo)
                page = doc[0]
                
                # Estratégia de recorte: Pega apenas os 40% superiores da página (onde fica o cabeçalho)
                rect = page.rect
                clip_rect = fitz.Rect(0, 0, rect.width, rect.height * 0.4)
                texto = page.get_text("text", clip=clip_rect).strip()
                
                # Fallback: se por acaso vier vazio (alguns PDFs mal formatados), pega os primeiros 600 caracteres
                if len(texto) < 30:
                    texto = page.get_text("text")[:600].strip()
                    
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
                            self.log_signal.emit(f"   ! Nome já existe na pasta: {novo_nome}")
                    else:
                        self.log_signal.emit(f"   ? Resposta fora do padrão: {info}")
                
                # Pausa estratégica para evitar bloqueios de taxa (Rate Limit)
                time.sleep(4)

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
        self.resize(750, 600)
        self.thread = None
        
        # Fundo do aplicativo (Estética Frutiger Aero)
        self.setStyleSheet("""
            QWidget {
                background-color: #E0F2FE;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            #glassPanel {
                background-color: rgba(255, 255, 255, 180);
                border: 1px solid rgba(255, 255, 255, 200);
                border-radius: 12px;
            }
            QLabel {
                background: transparent;
            }
            QLineEdit, QComboBox {
                background-color: rgba(255, 255, 255, 220);
                border: 1px solid #7DD3FC;
                border-radius: 6px;
                padding: 6px;
                selection-background-color: #38BDF8;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 2px solid #0EA5E9;
                background-color: white;
            }
            QTextEdit {
                background-color: rgba(255, 255, 255, 230);
                border: 1px solid #BAE6FD;
                border-radius: 6px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 12px;
            }
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E0F2FE, stop:1 #BAE6FD);
                border: 1px solid #7DD3FC;
                border-radius: 6px;
                padding: 8px 15px;
                color: #0369A1;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F0F9FF, stop:1 #E0F2FE);
                border: 1px solid #38BDF8;
            }
            QPushButton:pressed {
                background-color: #BAE6FD;
            }
            #btnIniciar {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #D1FAE5, stop:1 #A7F3D0);
                border: 1px solid #34D399;
                color: #064E3B;
                font-size: 14px;
                padding: 10px;
            }
            #btnIniciar:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #A7F3D0, stop:1 #6EE7B7);
            }
            #btnIniciar:disabled {
                background-color: #E2E8F0;
                border: 1px solid #CBD5E1;
                color: #94A3B8;
            }
        """)
        
        self.setup_ui()
        self.carregar_config()
        self.atualizar_visibilidade_modelo() # Chama na inicialização para ajustar os campos

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Container Aero Glass
        self.glass_panel = QWidget()
        self.glass_panel.setObjectName("glassPanel")
        glass_layout = QVBoxLayout(self.glass_panel)
        glass_layout.setSpacing(15)
        glass_layout.setContentsMargins(20, 20, 20, 20)
        
        # Sombra suave para o painel
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 30))
        shadow.setOffset(0, 8)
        self.glass_panel.setGraphicsEffect(shadow)

        # Cabeçalho
        header_layout = QHBoxLayout()
        lbl_titulo = QLabel("Renomeador de Artigos Científicos")
        lbl_titulo.setStyleSheet("font-size: 22px; font-weight: bold; color: #075985;")
        
        sombra_texto = QGraphicsDropShadowEffect()
        sombra_texto.setBlurRadius(2)
        sombra_texto.setColor(QColor(255, 255, 255, 255))
        sombra_texto.setOffset(1, 1)
        lbl_titulo.setGraphicsEffect(sombra_texto)

        self.btn_ajuda = QPushButton("❓ Central de Ajuda")
        self.btn_ajuda.setCursor(Qt.PointingHandCursor)
        self.btn_ajuda.clicked.connect(self.mostrar_ajuda)
        
        header_layout.addWidget(lbl_titulo)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_ajuda)
        glass_layout.addLayout(header_layout)

        # Linha separadora
        linha = QWidget()
        linha.setFixedHeight(2)
        linha.setStyleSheet("background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(14, 165, 233, 0), stop:0.5 rgba(14, 165, 233, 100), stop:1 rgba(14, 165, 233, 0));")
        glass_layout.addWidget(linha)

        # Controles de API
        grid_api = QVBoxLayout()
        
        # Linha 1: Provedor e Chave
        row1_layout = QHBoxLayout()
        
        lbl_provedor = QLabel("Provedor de IA:")
        lbl_provedor.setFixedWidth(100)
        lbl_provedor.setStyleSheet("font-weight: bold; color: #0369A1;")
        
        self.combo_provedor = QComboBox()
        self.combo_provedor.addItems(["Google AI Studio", "OpenRouter"])
        self.combo_provedor.currentTextChanged.connect(self.atualizar_visibilidade_modelo)
        
        lbl_api = QLabel("  Chave API:")
        lbl_api.setStyleSheet("font-weight: bold; color: #0369A1;")
        
        self.input_api = QLineEdit()
        self.input_api.setEchoMode(QLineEdit.Password)
        self.input_api.setPlaceholderText("Cole sua chave secreta aqui...")
        
        row1_layout.addWidget(lbl_provedor)
        row1_layout.addWidget(self.combo_provedor)
        row1_layout.addWidget(lbl_api)
        row1_layout.addWidget(self.input_api, 1) 
        grid_api.addLayout(row1_layout)
        
        # Linha 2: Modelo Condicional (Só aparece no OpenRouter)
        self.row_modelo_layout = QHBoxLayout()
        self.lbl_modelo = QLabel("Modelo (LLM):")
        self.lbl_modelo.setFixedWidth(100)
        self.lbl_modelo.setStyleSheet("font-weight: bold; color: #0369A1;")
        
        self.input_modelo = QLineEdit()
        self.input_modelo.setText("google/gemini-2.5-flash:free") # Padrão gratuito do OpenRouter
        self.input_modelo.setToolTip("Digite a tag exata do modelo do OpenRouter.")
        
        self.row_modelo_layout.addWidget(self.lbl_modelo)
        self.row_modelo_layout.addWidget(self.input_modelo)
        
        grid_api.addLayout(self.row_modelo_layout)
        glass_layout.addLayout(grid_api)

        # Pasta
        layout_pasta = QHBoxLayout()
        lbl_pasta = QLabel("Pasta (PDFs):")
        lbl_pasta.setFixedWidth(100)
        lbl_pasta.setStyleSheet("font-weight: bold; color: #0369A1;")
        
        self.input_pasta = QLineEdit()
        self.input_pasta.setPlaceholderText("Selecione o diretório contendo os artigos...")
        
        self.btn_procurar = QPushButton("📂 Procurar...")
        self.btn_procurar.setCursor(Qt.PointingHandCursor)
        self.btn_procurar.clicked.connect(self.selecionar_pasta)
        
        layout_pasta.addWidget(lbl_pasta)
        layout_pasta.addWidget(self.input_pasta)
        layout_pasta.addWidget(self.btn_procurar)
        glass_layout.addLayout(layout_pasta)

        # Botão Iniciar
        self.btn_iniciar = QPushButton("🚀 INICIAR PROCESSAMENTO")
        self.btn_iniciar.setObjectName("btnIniciar")
        self.btn_iniciar.setCursor(Qt.PointingHandCursor)
        self.btn_iniciar.clicked.connect(self.iniciar_processo)
        glass_layout.addWidget(self.btn_iniciar)

        # Log
        lbl_log = QLabel("Registro de Atividades (Log):")
        lbl_log.setStyleSheet("font-weight: bold; color: #075985; margin-top: 5px;")
        glass_layout.addWidget(lbl_log)
        
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        glass_layout.addWidget(self.txt_log)

        # Autoria
        lbl_autoria = QLabel("Desenvolvido por Philipe - GitHub @oldboy465")
        lbl_autoria.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl_autoria.setStyleSheet("font-size: 11px; color: #64748B; font-style: italic; background: transparent;")
        glass_layout.addWidget(lbl_autoria)

        main_layout.addWidget(self.glass_panel)

    def atualizar_visibilidade_modelo(self):
        """Oculta ou exibe o campo de modelo dependendo do provedor escolhido"""
        provedor = self.combo_provedor.currentText()
        if provedor == "Google AI Studio":
            self.lbl_modelo.hide()
            self.input_modelo.hide()
        elif provedor == "OpenRouter":
            self.lbl_modelo.show()
            self.input_modelo.show()

    def carregar_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    dados = json.load(f)
                    chave_salva = dados.get("api_key", "")
                    provedor_salvo = dados.get("provider", "Google AI Studio")
                    pasta_salva = dados.get("pasta", "")
                    modelo_or_salvo = dados.get("model_or", "")
                    
                    if chave_salva:
                        resposta = QMessageBox.question(
                            self, 'Sessão Anterior Encontrada', 
                            'Deseja carregar suas configurações e chave API da última utilização?',
                            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                        )
                        
                        if resposta == QMessageBox.Yes:
                            self.combo_provedor.setCurrentText(provedor_salvo)
                            self.input_api.setText(chave_salva)
                            if pasta_salva and os.path.exists(pasta_salva):
                                self.input_pasta.setText(pasta_salva)
                            if modelo_or_salvo:
                                self.input_modelo.setText(modelo_or_salvo)
            except Exception as e:
                print(f"Erro ao ler config: {e}")

    def salvar_config(self, provider, chave, pasta, model_or):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({
                    "provider": provider,
                    "api_key": chave,
                    "pasta": pasta,
                    "model_or": model_or
                }, f)
        except Exception as e:
            print(f"Erro ao salvar config: {e}")

    def selecionar_pasta(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecione a pasta com os PDFs")
        if pasta:
            self.input_pasta.setText(os.path.normpath(pasta))

    def log(self, mensagem):
        self.txt_log.append(mensagem)
        scrollbar = self.txt_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def mostrar_ajuda(self):
        texto_ajuda = (
            "<div style='font-family: Arial;'>"
            "<h2 style='color: #0369A1;'>Bem-vindo ao Renomeador de Artigos!</h2>"
            "<p>Este sistema automatiza a tediosa tarefa de renomear artigos lendo a primeira página do PDF e extraindo os metadados usando Inteligência Artificial (padrão <b>Sobrenome - Ano.pdf</b>).</p>"
            "<hr>"
            "<h3 style='color: #0284C7;'>Opção 1: Usando Google AI Studio (Padrão)</h3>"
            "<ol>"
            "<li>Acesse <b>aistudio.google.com</b> e faça login.</li>"
            "<li>Vá em <b>Get API key</b> > <b>Create API key</b>.</li>"
            "<li>Cole a chave no programa. O modelo será configurado automaticamente.</li>"
            "</ol>"
            "<hr>"
            "<h3 style='color: #0284C7;'>Opção 2: Usando OpenRouter</h3>"
            "<ol>"
            "<li>Acesse <b>openrouter.ai</b> e crie sua conta.</li>"
            "<li>Vá em <b>Keys</b> e clique em <b>Create Key</b>.</li>"
            "<li>Mude o Provedor no programa para 'OpenRouter' e cole a chave.</li>"
            "<li><b>Atenção ao Modelo:</b> O campo 'Modelo' vai aparecer. O padrão já está preenchido como <i>google/gemini-2.5-flash:free</i>, mas você pode mudar caso deseje testar outra IA.</li>"
            "</ol>"
            "<hr>"
            "<h3 style='color: #0284C7;'>⚠️ Dicas Importantes:</h3>"
            "<ul>"
            "<li><b>Limites:</b> O programa pausa de propósito (4 a 5 segundos) entre os arquivos para que o provedor não bloqueie a sua chave por excesso de requisições.</li>"
            "<li>O processamento ocorre em segundo plano. Você pode arrastar a janela pro lado e continuar trabalhando.</li>"
            "</ul>"
            "</div>"
        )
        
        caixa_ajuda = QMessageBox(self)
        caixa_ajuda.setWindowTitle("Central de Ajuda e Instruções")
        caixa_ajuda.setIcon(QMessageBox.Information)
        caixa_ajuda.setTextFormat(Qt.RichText)
        caixa_ajuda.setText(texto_ajuda)
        caixa_ajuda.setStandardButtons(QMessageBox.Ok)
        caixa_ajuda.exec_()

    def iniciar_processo(self):
        provedor = self.combo_provedor.currentText()
        api_key = self.input_api.text().strip()
        pasta = self.input_pasta.text().strip()
        modelo_or = self.input_modelo.text().strip()

        if not api_key:
            QMessageBox.warning(self, "Aviso", "Por favor, insira a sua Chave API.")
            return
            
        if not pasta or not os.path.exists(pasta):
            QMessageBox.warning(self, "Aviso", "Por favor, selecione uma pasta válida.")
            return

        if provedor == "OpenRouter" and not modelo_or:
            QMessageBox.warning(self, "Aviso", "O campo 'Modelo' não pode ficar vazio ao usar o OpenRouter.")
            return

        self.salvar_config(provedor, api_key, pasta, modelo_or)

        # Define o modelo com base no provedor escolhido
        modelo_interno = "gemini-2.5-flash" if provedor == "Google AI Studio" else modelo_or

        # Prepara a interface
        self.btn_iniciar.setEnabled(False)
        self.btn_iniciar.setText("Processando... Aguarde a finalização")
        self.input_api.setEnabled(False)
        self.input_modelo.setEnabled(False)
        self.combo_provedor.setEnabled(False)
        self.input_pasta.setEnabled(False)
        self.btn_procurar.setEnabled(False)
        self.txt_log.clear()

        # Inicia a Thread passando o modelo definido internamente
        self.thread = RenomeadorThread(provedor, api_key, modelo_interno, pasta)
        self.thread.log_signal.connect(self.log)
        self.thread.finished_signal.connect(self.processo_finalizado)
        self.thread.start()

    def processo_finalizado(self):
        self.btn_iniciar.setEnabled(True)
        self.btn_iniciar.setText("🚀 INICIAR PROCESSAMENTO")
        self.input_api.setEnabled(True)
        self.input_modelo.setEnabled(True)
        self.combo_provedor.setEnabled(True)
        self.input_pasta.setEnabled(True)
        self.btn_procurar.setEnabled(True)
        QMessageBox.information(self, "Concluído", "O processamento de todos os arquivos foi finalizado com sucesso!")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())