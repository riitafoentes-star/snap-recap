# 🚀 Como Gerar o .exe no GitHub Actions

## Passo 1: Criar Repositório no GitHub

1. Acesse https://github.com/new
2. Preencha:
   - **Repository name**: `snap-recap` (ou o nome que preferir)
   - **Description**: "Desktop app para converter manga em vídeos recap"
   - **Visibility**: Private (recomendado) ou Public
3. **NÃO** marque "Add a README file" (já temos um)
4. Clique em **Create repository**

## Passo 2: Conectar seu Repositório Local ao GitHub

Copie e execute os comandos que o GitHub mostrar na tela, ou use estes (substitua `SEU_USUARIO` pelo seu username):

```bash
git remote add origin https://github.com/SEU_USUARIO/snap-recap.git
git branch -M main
git push -u origin main
```

**Exemplo:**
```bash
git remote add origin https://github.com/joaosilva/snap-recap.git
git branch -M main
git push -u origin main
```

## Passo 3: Aguardar o Build Automático

1. Após o push, acesse: `https://github.com/SEU_USUARIO/snap-recap/actions`
2. Você verá o workflow "Build Tauri App" rodando
3. Aguarde ~10-15 minutos (primeira build demora mais)
4. Quando terminar, verá um ✅ verde

## Passo 4: Baixar o .exe

### Opção A: Dos Artifacts (Build Individual)
1. Clique no workflow que terminou
2. Role até "Artifacts" no final da página
3. Baixe **windows-build.zip**
4. Extraia e encontre o `.exe` dentro

### Opção B: Criar uma Release (Recomendado)
1. Vá em `https://github.com/SEU_USUARIO/snap-recap/releases`
2. Clique em **"Create a new release"**
3. Preencha:
   - **Tag**: `v0.1.0`
   - **Title**: `Snap Recap v0.1.0`
   - **Description**: Descreva as funcionalidades
4. Arraste o `.exe` dos artifacts para a área de upload
5. Clique em **"Publish release"**

## 📦 O que será gerado

### Windows
- `Snap Recap_0.1.0_x64-setup.exe` - Instalador NSIS
- `Snap Recap_0.1.0_x64_en-US.msi` - Instalador MSI

### Linux (bonus)
- `Snap Recap_0.1.0_amd64.deb` - Debian/Ubuntu
- `Snap Recap-0.1.0-1.x86_64.rpm` - Fedora/RHEL

## 🔧 Troubleshooting

### Se o build falhar:
1. Verifique os logs no GitHub Actions
2. Erros comuns:
   - **Falta de ícones**: Já resolvido ✅
   - **Dependências Python**: Adicione ao workflow se necessário
   - **Binário Python faltando**: O placeholder já está criado ✅

### Para builds futuros:
Sempre que fizer mudanças e quiser um novo `.exe`:
```bash
git add .
git commit -m "Descrição das mudanças"
git push
```

O GitHub Actions vai rodar automaticamente!

## 💡 Dicas

- **Primeira build**: ~15 minutos
- **Builds seguintes**: ~5-8 minutos (cache)
- **Artifacts expiram**: 90 dias (padrão GitHub)
- **Releases não expiram**: Use para versões importantes

## 🎯 Próximos Passos

Depois de ter o `.exe`:
1. Teste em uma máquina Windows limpa
2. Verifique se todas as funcionalidades funcionam
3. Crie releases para cada versão estável
4. Compartilhe o link da release com clientes

---

**Precisa de ajuda?** Abra uma issue no repositório ou me chame! 😊
