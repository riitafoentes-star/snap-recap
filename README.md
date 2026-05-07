# Snap Recap

Aplicação desktop para converter manga/manhwa em vídeos recap profissionais automaticamente.

## 🚀 Funcionalidades

- **Ingestion**: Download e processamento de páginas de manga
- **Intelligence**: Upscaling de imagens, geração de roteiro e narração com IA
- **Production**: Montagem de vídeo com motion, legendas e exportação

## 📦 Download

Baixe a versão mais recente na [página de Releases](../../releases).

### Windows
- `Snap-Recap_x.x.x_x64-setup.exe` - Instalador Windows

### Linux
- `snap-recap_x.x.x_amd64.deb` - Debian/Ubuntu
- `snap-recap-x.x.x-1.x86_64.rpm` - Fedora/RHEL

## 🛠️ Desenvolvimento

### Pré-requisitos
- Node.js 20+
- Python 3.11+
- Rust (para build do Tauri)

### Instalação
```bash
npm install
pip install -e src-python
```

### Executar em desenvolvimento
```bash
npm run dev
```

### Build
```bash
npm run tauri build
```

## 📝 Configuração

Copie `.env.example` para `.env` e configure suas chaves de API:
- OpenRouter / Groq / Ollama (para geração de roteiro)
- ElevenLabs (para narração)

## 📄 Licença

Proprietary - Todos os direitos reservados
