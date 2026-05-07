# Implementation Plan: Snap Recap App (recap-synth-app)

## Overview

Implementação incremental do pipeline end-to-end: setup do projeto → modelos de dados → componentes Python do pipeline (Ingestion → Intelligence → Production) → bridge IPC Tauri → UI React. Cada tarefa constrói sobre a anterior e termina com integração funcional.

Stack: Python (backend/sidecar) + Tauri 2 + React 18 + TypeScript + Tailwind CSS.

---

## Tasks

- [x] 1. Setup do projeto e estrutura de pastas
  - Criar `pyproject.toml` com dependências Python (opencv-python, numpy, moviepy, ffmpeg-python, openai-whisper, realesrgan, httpx, pydantic, hypothesis, google-generativeai, google-api-python-client, python-dotenv)
  - Criar `src-tauri/` com `tauri.conf.json` configurado para sidecar Python e permissões IPC
  - Criar `package.json` com dependências frontend (react, typescript, tailwindcss, zustand, shadcn/ui, @tauri-apps/api)
  - Criar estrutura de pastas: `src/` (frontend), `src-python/` (backend), `src-tauri/` (Rust shell)
  - Criar `src-python/__init__.py`, `src-python/pipeline/`, `src-python/providers/`, `src-python/tests/`
  - Criar `.env.example` com placeholders para todas as API keys necessárias
  - _Requirements: 14.1_

- [x] 2. Modelos de dados Python
  - [x] 2.1 Implementar dataclasses core em `src-python/models.py`
    - `BoundingBox` com propriedade `aspect_ratio` e método `to_16x9`
    - `Panel`, `CroppedPanel`, `UpscaledImage`, `BubbleRegion`
    - `PageImage`, `PageSource`
    - `ScriptSegment`, `Script`
    - `AudioSegment`
    - `KenBurnsParams`, `TimelineClip`, `Timeline`
    - `PipelineConfig`, `IngestionConfig`, `IntelligenceConfig`, `ProductionConfig`, `ExportConfig`
    - `JobResult`, `JobStatus` (enum: SUCCESS, FAILED, PARTIAL)
    - `JobSummary`, `PhaseContext`, `PhaseResult`, `ProductionAssets`, `IntelligenceResult`, `PanelSet`
    - Usar `pydantic` para validação onde aplicável
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ]* 2.2 Escrever testes unitários para os modelos de dados
    - Testar `BoundingBox.aspect_ratio` e `to_16x9`
    - Testar validação de campos obrigatórios
    - _Requirements: 4.4, 4.5_

- [x] 3. StateManager
  - [x] 3.1 Implementar `StateManager` em `src-python/state_manager.py`
    - `save_checkpoint(job_id, phase, data)` — serializar com `json` ou `pickle` em `output_dir/{job_id}/{phase}.checkpoint`
    - `load_checkpoint(job_id, phase)` — retornar `None` se não existir, sem lançar exceção
    - `get_job_status(job_id)` — retornar `JobStatus` baseado nos checkpoints existentes
    - `list_jobs()` — listar todos os jobs com metadados
    - Garantir que API keys e tokens OAuth nunca sejam serializados nos checkpoints
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 14.1_

  - [ ]* 3.2 Escrever property test para checkpoint round-trip (Property 1)
    - **Property 1: Checkpoint round-trip**
    - **Validates: Requirements 2.1, 2.2**

  - [ ]* 3.3 Escrever property test para ausência de credenciais em checkpoints (Property 3)
    - **Property 3: Checkpoints não contêm credenciais**
    - **Validates: Requirements 2.5, 14.1**

- [x] 4. PluginRegistry e interfaces de providers
  - [x] 4.1 Implementar `PluginRegistry` em `src-python/plugin_registry.py`
    - Definir `LLMProvider` e `TTSProvider` como `Protocol` em `src-python/providers/base.py`
    - `register_llm(name, provider)` e `register_tts(name, provider)`
    - `resolve_llm(name)` e `resolve_tts(name)` — lançar exceção descritiva para nome inválido
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 4.2 Implementar providers LLM em `src-python/providers/llm/`
    - `GeminiProvider` usando `google-generativeai`
    - `OllamaProvider` usando `httpx`
    - `GroqProvider` usando `httpx`
    - `OpenRouterProvider` usando `httpx`
    - Cada provider implementa `LLMProvider.complete(messages, config) -> str`
    - _Requirements: 5.3, 10.1_

  - [x] 4.3 Implementar providers TTS em `src-python/providers/tts/`
    - `ElevenLabsProvider` usando `httpx`
    - `LocalTTSProvider` (fallback offline)
    - Cada provider implementa `TTSProvider.synthesize(text, voice_id) -> bytes`
    - _Requirements: 6.4, 10.2_

  - [ ]* 4.4 Escrever testes unitários para PluginRegistry
    - Testar registro e resolução de providers
    - Testar exceção para nome inválido com mensagem descritiva
    - _Requirements: 10.3, 10.4_

- [x] 5. PageDownloader
  - [x] 5.1 Implementar `PageDownloader` em `src-python/pipeline/ingestion/page_downloader.py`
    - `download_chapter(chapter_id)` — chamar MangaDex API com `httpx`, retornar `List[PageImage]`
    - Implementar retry com exponential backoff (máx 3 tentativas) para erros 429 e 404
    - `from_local(paths)` — carregar imagens de paths locais, retornar `List[PageImage]`
    - Validar paths contra path traversal (`../`, `..\`) antes de qualquer acesso ao filesystem
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 14.3, 14.4_

  - [ ]* 5.2 Escrever property test para upload local preserva quantidade (Property 4)
    - **Property 4: Upload local preserva quantidade de páginas**
    - **Validates: Requirements 3.3**

  - [ ]* 5.3 Escrever property test para rejeição de path traversal (Property 17)
    - **Property 17: Path traversal é rejeitado**
    - **Validates: Requirements 3.4, 14.3**

- [x] 6. PanelDetector
  - [x] 6.1 Implementar `PanelDetector` em `src-python/pipeline/ingestion/panel_detector.py`
    - `detect(page)` — usar OpenCV: `cvtColor`, `threshold`, `morphologyEx`, `findContours`, `boundingRect`
    - Filtrar contornos por `MIN_PANEL_AREA` e `MAX_ASPECT_RATIO`
    - Retornar `List[BoundingBox]` ordenados por `(y, x)` (ordem de leitura)
    - Garantir que bboxes retornados sejam não-sobrepostos
    - _Requirements: 4.1, 4.2_

  - [ ]* 6.2 Escrever property test para painéis não-sobrepostos (Property 5)
    - **Property 5: Painéis detectados são não-sobrepostos**
    - **Validates: Requirements 4.1**

  - [ ]* 6.3 Escrever property test para ordem de leitura (Property 6)
    - **Property 6: Painéis detectados estão em ordem de leitura**
    - **Validates: Requirements 4.2**

- [x] 7. BubbleSeparator
  - [x] 7.1 Implementar `BubbleSeparator` em `src-python/pipeline/ingestion/bubble_separator.py`
    - `separate(page, panels)` — isolar regiões de balões de fala usando OpenCV (detecção de contornos brancos/elípticos)
    - Retornar painéis com `art_region` (sem balões) e `bubble_regions` preenchidos
    - Garantir que `art_region ∪ bubble_regions` cobre o bbox original de cada painel
    - _Requirements: 4.3_

  - [ ]* 7.2 Escrever property test para cobertura do bbox (Property 7)
    - **Property 7: BubbleSeparator preserva cobertura do bbox**
    - **Validates: Requirements 4.3**

- [x] 8. SmartCropper
  - [x] 8.1 Implementar `SmartCropper` em `src-python/pipeline/ingestion/smart_cropper.py`
    - `crop_to_16x9(panel, target_width=1920)` — calcular escala para cobrir canvas 16:9, centralizar crop
    - Usar `cv2.resize` com `INTER_LANCZOS4` para qualidade máxima
    - Retornar `CroppedPanel` com `image.shape[1] == target_width` e aspect ratio 16:9 (±1px)
    - _Requirements: 4.4, 4.5_

  - [ ]* 8.2 Escrever property test para aspect ratio 16:9 (Property 8)
    - **Property 8: SmartCropper produz aspect ratio 16:9**
    - **Validates: Requirements 4.4, 4.5**

- [x] 9. IngestionPhase
  - [x] 9.1 Implementar `IngestionPhase` em `src-python/pipeline/ingestion/phase.py`
    - `run(source, config)` — orquestrar `PageDownloader → PanelDetector → BubbleSeparator → SmartCropper`
    - Retornar `PanelSet` com todos os painéis processados
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 9.2 Escrever testes de integração para IngestionPhase
    - Testar com imagem sintética de manga (gerada com numpy)
    - Verificar que o PanelSet retornado tem painéis com aspect ratio 16:9
    - _Requirements: 3.3, 4.4_

- [ ] 10. Checkpoint: Ingestion completa
  - Garantir que todos os testes da fase Ingestion passam
  - Verificar que `StateManager.save_checkpoint` persiste corretamente o `PanelSet`
  - Perguntar ao usuário se há dúvidas antes de prosseguir para Intelligence.

- [x] 11. ScriptGenerator
  - [x] 11.1 Implementar `ScriptGenerator` em `src-python/pipeline/intelligence/script_generator.py`
    - `generate(panels, prompt, model)` — processar painéis em batches, chamar `LLMProvider.complete`
    - Construir prompt com imagens em base64 e contexto dos últimos 3 segmentos
    - Parsear resposta do LLM em `List[ScriptSegment]` com `narration` não-vazia
    - Tentar provider alternativo em caso de timeout ou quota excedida
    - Garantir `len(segments) == len(panels)` e `sum(duration_hints) > 0`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 11.2 Escrever property test para script com um segmento por painel (Property 9)
    - **Property 9: Script tem um segmento por painel**
    - **Validates: Requirements 5.1, 5.2**

- [x] 12. VoiceGenerator
  - [x] 12.1 Implementar `VoiceGenerator` em `src-python/pipeline/intelligence/voice_generator.py`
    - `synthesize(script, provider)` — iterar segmentos, chamar `TTSProvider.synthesize`
    - Retornar `List[AudioSegment]` com `len == len(script.segments)`
    - Garantir formato WAV 44.1kHz para todos os segmentos
    - Registrar erro com contexto do segmento e retornar `JobResult(FAILED)` se provider falhar
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 12.2 Escrever property test para áudio com um segmento por ScriptSegment (Property 10)
    - **Property 10: Áudio tem um segmento por ScriptSegment**
    - **Validates: Requirements 6.1, 6.3**

  - [ ]* 12.3 Escrever property test para duração do áudio respeita duration_hint (Property 11)
    - **Property 11: Duração do áudio respeita duration_hint**
    - **Validates: Requirements 6.2**

- [x] 13. ImageUpscaler
  - [x] 13.1 Implementar `ImageUpscaler` em `src-python/pipeline/intelligence/image_upscaler.py`
    - `upscale(panel, model)` — usar Real-ESRGAN ou Waifu2x conforme `config.upscale_model`
    - Retornar `UpscaledImage` com resolução ≥ 1920×1080
    - Tratar OOM: reduzir batch size automaticamente e tentar com fator menor
    - Fallback: usar imagem original sem upscale e registrar aviso no log
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 13.2 Escrever property test para resolução mínima da UpscaledImage (Property 12)
    - **Property 12: UpscaledImage tem resolução mínima**
    - **Validates: Requirements 7.1**

- [x] 14. IntelligencePhase
  - [x] 14.1 Implementar `IntelligencePhase` em `src-python/pipeline/intelligence/phase.py`
    - `run(panels, config)` — orquestrar `ScriptGenerator`, `VoiceGenerator`, `ImageUpscaler` (upscale em paralelo com `ThreadPoolExecutor`)
    - Retornar `IntelligenceResult(script, audio_segments, upscaled)`
    - _Requirements: 5.1, 6.1, 7.1_

  - [ ]* 14.2 Escrever testes de integração para IntelligencePhase com mocks
    - Usar mocks para LLMProvider e TTSProvider
    - Verificar que `IntelligenceResult` tem listas com mesmo comprimento que `panels`
    - _Requirements: 5.1, 6.1, 7.1_

- [x] 15. TimelineAssembler
  - [x] 15.1 Implementar `TimelineAssembler` em `src-python/pipeline/production/timeline_assembler.py`
    - `assemble(panels, audio, script)` — criar `TimelineClip` para cada painel com `start_time` e `end_time` não-sobrepostos
    - Garantir `total_duration == sum(a.duration for a in audio)`
    - Garantir `len(timeline.clips) == len(panels)`
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ]* 15.2 Escrever property test para timeline com um clipe por painel (Property 13)
    - **Property 13: Timeline tem um clipe por painel**
    - **Validates: Requirements 8.1**

  - [ ]* 15.3 Escrever property test para clipes não-sobrepostos (Property 14)
    - **Property 14: Clipes da timeline não se sobrepõem**
    - **Validates: Requirements 8.2**

  - [ ]* 15.4 Escrever property test para duração total consistente (Property 15)
    - **Property 15: Duração total da timeline é consistente**
    - **Validates: Requirements 8.3**

- [x] 16. MotionEngine (Ken Burns)
  - [x] 16.1 Implementar `MotionEngine` em `src-python/pipeline/production/motion_engine.py`
    - `apply_ken_burns(clip, params, fps)` — gerar frames com zoom/pan interpolados via `lerp`
    - Suportar easing `linear` e `ease_in_out` (cubic)
    - Garantir que zoom em cada frame está em `[start_zoom, end_zoom]`
    - Usar `cv2.resize` com `INTER_LINEAR` para performance
    - _Requirements: 8.4, 8.5_

  - [ ]* 16.2 Escrever property test para zoom dentro do intervalo (Property 16)
    - **Property 16: Ken Burns zoom permanece no intervalo configurado**
    - **Validates: Requirements 8.4, 8.5**

- [x] 17. SubtitleBurner
  - [x] 17.1 Implementar `SubtitleBurner` em `src-python/pipeline/production/subtitle_burner.py`
    - `transcribe_and_burn(video, audio_segments)` — usar `openai-whisper` para transcrever cada `AudioSegment`
    - Gerar pelo menos um bloco SRT por `AudioSegment`
    - Queimar legendas no vídeo com `moviepy` ou `ffmpeg-python`
    - _Requirements: 8.6_

- [x] 18. VideoExporter
  - [x] 18.1 Implementar `VideoExporter` em `src-python/pipeline/production/video_exporter.py`
    - `export_mp4(timeline, output, config)` — montar e exportar via FFmpeg, verificar código de retorno
    - `export_otioz(timeline, output)` — gerar arquivo `.OTIOZ` parseável por OpenTimelineIO
    - Tratar erro FFmpeg: capturar stderr, logar comando completo, tentar preset menor
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 18.2 Implementar `YouTubeUploader` em `src-python/pipeline/production/youtube_uploader.py`
    - `upload(video, metadata, credentials)` — usar YouTube Data API v3 via `google-api-python-client`
    - Armazenar tokens OAuth com permissões 600 no filesystem
    - Retornar URL do vídeo publicado
    - _Requirements: 9.5, 14.2_

- [x] 19. ProductionPhase
  - [x] 19.1 Implementar `ProductionPhase` em `src-python/pipeline/production/phase.py`
    - `run(assets, config)` — orquestrar `TimelineAssembler → MotionEngine → SubtitleBurner → VideoExporter`
    - Chamar `YouTubeUploader` se `config.upload_youtube == True`
    - Retornar `VideoArtifact` com paths dos arquivos exportados
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 20. PipelineOrchestrator
  - [x] 20.1 Implementar `PipelineOrchestrator` em `src-python/pipeline/orchestrator.py`
    - `run_pipeline(config)` — executar Ingestion → Intelligence → Production com checkpoints via `StateManager`
    - `resume_job(job_id)` — carregar checkpoint e pular fases já concluídas
    - `cancel_job(job_id)` — sinalizar cancelamento e preservar checkpoints existentes
    - `run_phase(phase, context)` — executar fase individual
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 20.2 Escrever property test para retomada sem reprocessamento (Property 2)
    - **Property 2: Retomada sem reprocessamento**
    - **Validates: Requirements 1.5, 2.2**

  - [ ]* 20.3 Escrever testes de integração para pipeline end-to-end com mocks
    - Testar fluxo completo com mocks para todos os providers externos
    - Verificar que `JobResult.status == SUCCESS` e `output_files` não-vazio
    - _Requirements: 1.1, 1.2_

- [ ] 21. Checkpoint: Pipeline Python completo
  - Garantir que todos os testes Python passam (`pytest src-python/tests/`)
  - Verificar que o pipeline end-to-end funciona com mocks
  - Perguntar ao usuário se há dúvidas antes de prosseguir para o frontend.

- [x] 22. Tauri sidecar bridge (IPC)
  - [x] 22.1 Implementar entry point do sidecar Python em `src-python/main.py`
    - Receber comandos via stdin (JSON-RPC ou protocolo Tauri sidecar)
    - Emitir eventos de progresso via stdout para a UI
    - Instanciar `PipelineOrchestrator` e despachar comandos: `run_pipeline`, `resume_job`, `cancel_job`
    - _Requirements: 11.4, 12.2, 12.4_

  - [x] 22.2 Implementar Tauri Commands em `src-tauri/src/commands.rs`
    - `run_pipeline(config)` — invocar sidecar Python e retornar `JobResult`
    - `cancel_job(job_id)` — enviar sinal de cancelamento ao sidecar
    - `get_job_status(job_id)` — consultar status do job
    - Configurar sidecar em `tauri.conf.json` com permissões de filesystem e shell
    - _Requirements: 11.4, 12.2, 12.4_

  - [x] 22.3 Implementar event listeners no frontend em `src/lib/ipc.ts`
    - Funções tipadas para invocar cada Tauri Command
    - Listener para eventos de progresso do pipeline (`pipeline:progress`, `pipeline:log`, `pipeline:done`)
    - Tipos TypeScript espelhando os modelos Python (`PipelineConfig`, `JobResult`, `ProgressEvent`)
    - _Requirements: 12.1, 12.2_

- [ ] 23. UI: Design tokens e NavigationSidebar
  - [ ] 23.1 Configurar design tokens em `src/styles/tokens.css`
    - Variáveis CSS para `bg.base`, `bg.surface`, `bg.elevated`, `accent.*`, `text.*`, `border`
    - Configurar Tailwind para usar as variáveis CSS
    - _Requirements: 11.1_

  - [ ] 23.2 Implementar `NavigationSidebar` em `src/components/NavigationSidebar.tsx`
    - Ícones para Ingestion (🔲), Intelligence (📋), Production (🎬), Settings (⚙)
    - Ícone ativo destacado com `accent.primary`
    - Fases bloqueadas (sem dados) exibidas como desabilitadas
    - Integrar com Zustand store para estado de navegação
    - _Requirements: 11.1_

  - [ ] 23.3 Implementar Zustand store em `src/store/pipelineStore.ts`
    - Estado global: `currentPhase`, `panelSet`, `jobId`, `jobStatus`, `progressMap`
    - Actions: `setPhase`, `setPanelSet`, `updateProgress`, `setJobStatus`
    - _Requirements: 11.4, 12.2_

- [ ] 24. UI: Tela SMART_STITCH.MOD (Ingestion)
  - [ ] 24.1 Implementar `MangaPageViewer` em `src/components/ingestion/MangaPageViewer.tsx`
    - Scroll vertical com páginas em tiras longas
    - Overlay colorido nos painéis detectados ao hover
    - Suporte a zoom e pan
    - Sincronizar painel selecionado com `ImageExplorer`
    - _Requirements: 11.1, 11.2_

  - [ ] 24.2 Implementar `ImageExplorer` em `src/components/ingestion/ImageExplorer.tsx`
    - Grid de thumbnails 16:9 dos painéis recortados
    - Clique seleciona painel e sincroniza destaque no `MangaPageViewer`
    - Drag-and-drop para reordenação (usar `@dnd-kit/core` ou similar)
    - _Requirements: 11.2, 11.3_

  - [ ] 24.3 Implementar `BottomBar` e tela `IngestionScreen` em `src/screens/IngestionScreen.tsx`
    - Seletor de FPS, contador de painéis detectados
    - Botão "Confirm" que invoca `run_pipeline` via IPC e navega para Intelligence
    - Barra de progresso no header durante estado `loading`
    - Estados: `idle`, `loading`, `review`, `confirmed`
    - _Requirements: 11.4, 11.5_

- [ ] 25. UI: Tela Intelligence (Processing)
  - [ ] 25.1 Implementar `PhaseProgressList` em `src/components/intelligence/PhaseProgressList.tsx`
    - Lista de tarefas paralelas: Script Generation, Voice Synthesis, Image Upscale
    - Barra de progresso individual com percentual e nome do provider ativo
    - Status visual: pending / running / done / error
    - _Requirements: 12.1_

  - [ ] 25.2 Implementar `LiveLogPanel` em `src/components/intelligence/LiveLogPanel.tsx`
    - Terminal-style com auto-scroll
    - Receber eventos `pipeline:log` via Tauri events em tempo real
    - _Requirements: 12.2_

  - [ ] 25.3 Implementar tela `IntelligenceScreen` em `src/screens/IntelligenceScreen.tsx`
    - Compor `PhaseProgressList` + `LiveLogPanel`
    - Botão "Cancel" durante processamento → invocar `cancel_job` via IPC
    - Botão "Continue to Production" habilitado quando todas as tarefas concluem
    - _Requirements: 12.3, 12.4_

- [ ] 26. UI: Tela TIMELINE_EDITOR (Production)
  - [ ] 26.1 Implementar `AssetPanel` em `src/components/production/AssetPanel.tsx`
    - Lista de clips com thumbnail, nome e duração
    - Clique seleciona clip e move playhead na timeline
    - _Requirements: 13.1_

  - [ ] 26.2 Implementar `VideoPreview` em `src/components/production/VideoPreview.tsx`
    - Preview de vídeo com controles play/pause, step frame, loop
    - Timecode no formato `HH:MM:SS:FF`
    - Atualizar frame ao arrastar playhead
    - _Requirements: 13.2_

  - [ ] 26.3 Implementar `Timeline` com trilhas em `src/components/production/Timeline.tsx`
    - `VideoTrack` (verde/`accent.success`), `AudioTrack` (vermelho/`accent.danger`), `SubtitleTrack` (azul/`accent.info`)
    - Scrubbing do playhead, zoom horizontal
    - Seleção de clip para edição de parâmetros Ken Burns
    - _Requirements: 13.1, 13.2_

  - [ ] 26.4 Implementar `ExportButton` e modal de exportação em `src/components/production/ExportModal.tsx`
    - Opções de formato: MP4, .OTIOZ, ambos
    - Opção de upload para YouTube
    - Barra de progresso FFmpeg durante exportação
    - Modal de sucesso com path do arquivo e link YouTube
    - _Requirements: 13.3, 13.4, 13.5_

  - [ ] 26.5 Implementar tela `ProductionScreen` em `src/screens/ProductionScreen.tsx`
    - Compor `AssetPanel` + `VideoPreview` + `Timeline` + `ExportButton`
    - Estados: `loading`, `ready`, `exporting`, `exported`
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

- [ ] 27. Checkpoint final — Garantir que todos os testes passam
  - Executar `pytest src-python/tests/ -v` e verificar que todos os testes passam
  - Executar `tsc --noEmit` no frontend e verificar ausência de erros de tipo
  - Perguntar ao usuário se há dúvidas antes de considerar a implementação concluída.

---

## Notes

- Tarefas marcadas com `*` são opcionais e podem ser puladas para MVP mais rápido
- Cada tarefa referencia requisitos específicos para rastreabilidade
- Property tests usam `hypothesis` e validam as 17 propriedades de corretude do design
- Os checkpoints (tarefas 10, 21, 27) garantem validação incremental antes de avançar
- O sidecar Python é empacotado com PyInstaller para distribuição junto ao app Tauri
