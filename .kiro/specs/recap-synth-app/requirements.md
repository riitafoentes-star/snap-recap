# Requirements Document

## Introduction

Snap Recap (anteriormente RecapSynth) é uma ferramenta de automação end-to-end para criação de vídeos de recap de manhwa/manga. O sistema ingere páginas de manhwa (via MangaDex API ou upload manual), processa painéis com visão computacional, gera roteiro e áudio com LLMs/TTS, aplica upscale nas imagens, monta uma timeline sincronizada com efeitos de movimento e exporta o vídeo final para editores profissionais ou diretamente para o YouTube.

O pipeline é dividido em três fases principais: **Ingestion** (detecção e extração de painéis), **Intelligence** (geração de conteúdo com IA) e **Production** (montagem e exportação do vídeo). A interface desktop é construída com Tauri + React e expõe as três fases como telas distintas: SMART_STITCH.MOD, Intelligence e TIMELINE_EDITOR.

---

## Glossary

- **App**: A aplicação desktop Snap Recap (Tauri + React + Python sidecar)
- **Pipeline**: O sistema de processamento end-to-end composto pelas fases Ingestion, Intelligence e Production
- **PipelineOrchestrator**: Componente Python que coordena a execução sequencial das três fases
- **StateManager**: Componente responsável por persistir e recuperar checkpoints do pipeline em disco
- **IngestionPhase**: Fase de download de páginas, detecção de painéis, separação de balões e recorte 16:9
- **PageDownloader**: Componente que obtém páginas via MangaDex API ou upload local
- **PanelDetector**: Componente de visão computacional (OpenCV) que detecta painéis em páginas de manga
- **BubbleSeparator**: Componente que isola regiões de balões de fala da arte dos painéis
- **SmartCropper**: Componente que recorta painéis para aspect ratio 16:9 sem distorção
- **IntelligencePhase**: Fase de geração de roteiro com LLM, síntese de voz e upscale de imagens
- **ScriptGenerator**: Componente que gera narração para cada painel usando um LLMProvider
- **VoiceGenerator**: Componente que sintetiza áudio a partir do script usando um TTSProvider
- **ImageUpscaler**: Componente que aumenta a resolução dos painéis com Real-ESRGAN ou Waifu2x
- **LLMProvider**: Interface (Protocol) para provedores de LLM (Gemini, Mistral, Ollama, Groq, OpenRouter)
- **TTSProvider**: Interface (Protocol) para provedores de TTS (ElevenLabs, OpenAI TTS, local)
- **ProductionPhase**: Fase de montagem de timeline, aplicação de efeitos e exportação de vídeo
- **TimelineAssembler**: Componente que monta a timeline sincronizando painéis, áudio e script
- **MotionEngine**: Componente que aplica Ken Burns effect nos clipes de imagem
- **SubtitleBurner**: Componente que transcreve áudio com Whisper e gera legendas SRT
- **VideoExporter**: Componente que exporta a timeline para MP4 (FFmpeg) e/ou .OTIOZ
- **YouTubeUploader**: Componente opcional que faz upload do vídeo via YouTube Data API v3
- **PluginRegistry**: Registro de implementações de provedores de IA resolvidas em runtime
- **ConfigManager**: Componente que gerencia configurações globais do pipeline
- **Panel**: Região de arte detectada em uma página de manga, com bbox, art_region e bubble_regions
- **CroppedPanel**: Painel recortado para aspect ratio 16:9
- **UpscaledImage**: Imagem de painel com resolução aumentada (≥ 1920×1080)
- **Script**: Conjunto de segmentos de narração gerados pelo LLM, um por painel
- **ScriptSegment**: Segmento individual de narração com texto, duração estimada e emoção
- **AudioSegment**: Arquivo de áudio WAV sintetizado para um ScriptSegment
- **Timeline**: Estrutura de dados com clipes sincronizados de vídeo, áudio e legendas
- **TimelineClip**: Clipe individual na timeline com painel, áudio, tempos e parâmetros Ken Burns
- **KenBurnsParams**: Parâmetros de zoom e pan para o efeito Ken Burns (start_zoom, end_zoom, start_pan, end_pan, easing)
- **JobResult**: Resultado final do pipeline com status, arquivos de saída e URL do YouTube
- **JobStatus**: Enum com valores SUCCESS, FAILED, PARTIAL
- **PipelineConfig**: Configuração completa de um job do pipeline
- **BoundingBox**: Retângulo delimitador (x, y, width, height) de um painel detectado
- **OTIOZ**: Formato de arquivo OpenTimelineIO compactado, compatível com Premiere Pro, Final Cut Pro e DaVinci Resolve
- **Ken Burns Effect**: Efeito de zoom e pan suave aplicado a imagens estáticas para criar movimento
- **IPC**: Inter-Process Communication entre a UI Tauri e o sidecar Python
- **Sidecar**: Processo Python empacotado com PyInstaller que executa o pipeline de IA

---

## Requirements

### Requirement 1: Orquestração do Pipeline

**User Story:** Como criador de conteúdo, quero executar o pipeline completo de processamento de manhwa em uma única operação, para que eu possa transformar capítulos brutos em vídeos narrados com o mínimo de esforço.

#### Acceptance Criteria

1. WHEN o usuário inicia um job com uma PipelineConfig válida, THE PipelineOrchestrator SHALL executar as fases Ingestion, Intelligence e Production em sequência
2. WHEN todas as fases concluem com sucesso, THE PipelineOrchestrator SHALL retornar um JobResult com status SUCCESS e a lista de arquivos de saída
3. IF qualquer fase falha com erro irrecuperável, THEN THE PipelineOrchestrator SHALL retornar um JobResult com status FAILED e a descrição do erro
4. WHEN o usuário solicita cancelamento de um job em execução, THE PipelineOrchestrator SHALL interromper o processamento e preservar os checkpoints das fases já concluídas
5. WHEN um job_id de um job parcialmente concluído é fornecido, THE PipelineOrchestrator SHALL retomar o pipeline a partir da última fase com checkpoint salvo, sem reprocessar fases anteriores

---

### Requirement 2: Persistência de Estado e Checkpoints

**User Story:** Como criador de conteúdo, quero que o processamento seja retomável após falhas, para que eu não perca o trabalho já realizado em caso de erro ou interrupção.

#### Acceptance Criteria

1. WHEN uma fase do pipeline conclui com sucesso, THE StateManager SHALL salvar um checkpoint com os dados da fase no diretório de saída do job
2. WHEN o StateManager é solicitado a carregar um checkpoint existente, THE StateManager SHALL retornar os dados equivalentes aos que foram salvos
3. IF um checkpoint não existe para uma fase, THEN THE StateManager SHALL retornar None sem lançar exceção
4. THE StateManager SHALL listar todos os jobs existentes com seus status e metadados
5. THE StateManager SHALL nunca serializar API keys ou credenciais OAuth nos arquivos de checkpoint

---

### Requirement 3: Ingestão de Páginas

**User Story:** Como criador de conteúdo, quero importar páginas de manhwa de diferentes fontes, para que eu possa trabalhar tanto com capítulos do MangaDex quanto com arquivos locais.

#### Acceptance Criteria

1. WHEN um chapter_id válido do MangaDex é fornecido, THE PageDownloader SHALL baixar todas as páginas do capítulo e retorná-las como uma lista de PageImages
2. IF a API do MangaDex retorna erro 429 (rate limit) ou 404 (não encontrado), THEN THE PageDownloader SHALL realizar até 3 tentativas com exponential backoff antes de retornar erro
3. WHEN uma lista de paths de arquivos locais válidos é fornecida, THE PageDownloader SHALL carregar as imagens e retorná-las como uma lista de PageImages com a mesma quantidade de elementos
4. IF um path de arquivo local contém sequências de path traversal (ex: `../`), THEN THE PageDownloader SHALL rejeitar o path e retornar erro de validação sem acessar o sistema de arquivos

---

### Requirement 4: Detecção e Processamento de Painéis

**User Story:** Como criador de conteúdo, quero que os painéis de manhwa sejam detectados e processados automaticamente, para que eu não precise recortar manualmente cada imagem.

#### Acceptance Criteria

1. WHEN uma PageImage válida é fornecida, THE PanelDetector SHALL retornar uma lista de BoundingBoxes não-sobrepostos representando os painéis detectados
2. WHEN painéis são detectados em uma página, THE PanelDetector SHALL retornar os BoundingBoxes ordenados de cima para baixo e da esquerda para a direita (ordem de leitura)
3. WHEN painéis e uma PageImage são fornecidos ao BubbleSeparator, THE BubbleSeparator SHALL retornar painéis onde a união de art_region e bubble_regions cobre o bbox original de cada painel
4. WHEN um Panel é fornecido ao SmartCropper, THE SmartCropper SHALL retornar um CroppedPanel com aspect ratio 16:9 (tolerância de ±1 pixel) sem distorção do conteúdo original
5. THE SmartCropper SHALL produzir CroppedPanels com largura igual ao target_width configurado (padrão: 1920 pixels)

---

### Requirement 5: Geração de Roteiro com LLM

**User Story:** Como criador de conteúdo, quero que o roteiro de narração seja gerado automaticamente a partir dos painéis, para que eu possa focar em refinamentos criativos em vez de escrever do zero.

#### Acceptance Criteria

1. WHEN um PanelSet não-vazio é fornecido ao ScriptGenerator, THE ScriptGenerator SHALL retornar um Script com exatamente um ScriptSegment por painel
2. THE ScriptGenerator SHALL garantir que cada ScriptSegment tenha narration não-vazia
3. WHEN o provedor LLM primário falha com timeout ou quota excedida, THE ScriptGenerator SHALL tentar o provedor LLM alternativo configurado antes de retornar erro
4. WHEN um Script válido é gerado, THE ScriptGenerator SHALL garantir que a soma dos duration_hints de todos os segmentos seja maior que zero
5. WHERE o idioma de saída está configurado, THE ScriptGenerator SHALL gerar narração no idioma especificado pelo BCP-47 language tag da PipelineConfig

---

### Requirement 6: Síntese de Voz

**User Story:** Como criador de conteúdo, quero que a narração seja sintetizada automaticamente com vozes de alta qualidade, para que o vídeo tenha áudio profissional sem gravação manual.

#### Acceptance Criteria

1. WHEN um Script válido é fornecido ao VoiceGenerator, THE VoiceGenerator SHALL retornar uma lista de AudioSegments com exatamente um segmento por ScriptSegment
2. WHEN um AudioSegment é sintetizado, THE VoiceGenerator SHALL garantir que a duração do áudio esteja dentro de ±20% do duration_hint do ScriptSegment correspondente
3. THE VoiceGenerator SHALL produzir todos os AudioSegments em formato WAV com sample rate de 44.1kHz
4. IF o TTSProvider retorna erro ou está indisponível, THEN THE VoiceGenerator SHALL registrar o erro com contexto do segmento e retornar JobResult com status FAILED

---

### Requirement 7: Upscale de Imagens

**User Story:** Como criador de conteúdo, quero que os painéis sejam upscalados para resolução Full HD, para que o vídeo final tenha qualidade visual adequada para publicação no YouTube.

#### Acceptance Criteria

1. WHEN um CroppedPanel é fornecido ao ImageUpscaler, THE ImageUpscaler SHALL retornar uma UpscaledImage com resolução mínima de 1920×1080 pixels
2. IF o ImageUpscaler encontra erro de Out of Memory ao processar um painel, THEN THE ImageUpscaler SHALL reduzir o batch size automaticamente e tentar novamente com fator de upscale menor
3. IF o upscale falha após todas as tentativas de recuperação, THEN THE ImageUpscaler SHALL usar a imagem original sem upscale como fallback e registrar um aviso no log
4. WHERE o modelo de upscale está configurado como "realesrgan" ou "waifu2x", THE ImageUpscaler SHALL utilizar o modelo correspondente para o processamento

---

### Requirement 8: Montagem da Timeline

**User Story:** Como criador de conteúdo, quero que a timeline de vídeo seja montada automaticamente sincronizando painéis e narração, para que eu tenha um vídeo coerente sem edição manual de timing.

#### Acceptance Criteria

1. WHEN listas de UpscaledImages, AudioSegments e Script com o mesmo número de elementos são fornecidas ao TimelineAssembler, THE TimelineAssembler SHALL retornar uma Timeline com exatamente len(panels) TimelineClips
2. WHEN uma Timeline é montada, THE TimelineAssembler SHALL garantir que nenhum par de TimelineClips tenha sobreposição entre start_time e end_time
3. WHEN uma Timeline é montada, THE TimelineAssembler SHALL garantir que total_duration seja igual à soma das durações de todos os AudioSegments
4. WHEN um TimelineClip é criado, THE MotionEngine SHALL aplicar Ken Burns effect com zoom interpolado suavemente de start_zoom para end_zoom em todos os frames do clipe
5. WHILE o Ken Burns effect está sendo aplicado, THE MotionEngine SHALL garantir que o valor de zoom em cada frame esteja dentro do intervalo [start_zoom, end_zoom]
6. WHEN os AudioSegments são fornecidos ao SubtitleBurner, THE SubtitleBurner SHALL gerar pelo menos um bloco de legenda SRT para cada AudioSegment via transcrição Whisper

---

### Requirement 9: Exportação de Vídeo

**User Story:** Como criador de conteúdo, quero exportar o vídeo em formatos compatíveis com editores profissionais e com o YouTube, para que eu possa publicar ou continuar editando conforme necessário.

#### Acceptance Criteria

1. WHEN o formato de exportação "mp4" é selecionado, THE VideoExporter SHALL produzir um arquivo MP4 válido via FFmpeg com a duração e resolução corretas
2. WHEN o formato de exportação "otioz" é selecionado, THE VideoExporter SHALL produzir um arquivo .OTIOZ parseável por OpenTimelineIO
3. WHEN o formato de exportação "both" é selecionado, THE VideoExporter SHALL produzir tanto o arquivo MP4 quanto o arquivo .OTIOZ
4. IF o FFmpeg retorna código de erro não-zero durante a exportação, THEN THE VideoExporter SHALL capturar o stderr do FFmpeg, registrar o comando completo para diagnóstico e tentar com preset de qualidade menor
5. WHERE o upload para YouTube está habilitado na PipelineConfig, THE YouTubeUploader SHALL fazer upload do arquivo MP4 via YouTube Data API v3 e retornar a URL do vídeo publicado

---

### Requirement 10: Registro de Provedores de IA

**User Story:** Como criador de conteúdo, quero poder trocar provedores de LLM e TTS sem alterar o pipeline, para que eu tenha flexibilidade para usar diferentes serviços conforme disponibilidade e custo.

#### Acceptance Criteria

1. THE PluginRegistry SHALL registrar implementações de LLMProvider por nome (ex: "gemini", "mistral", "ollama", "groq", "openrouter")
2. THE PluginRegistry SHALL registrar implementações de TTSProvider por nome (ex: "elevenlabs", "openai", "local")
3. WHEN um nome de provedor registrado é solicitado, THE PluginRegistry SHALL retornar a implementação correspondente sem erro
4. IF um nome de provedor não registrado é solicitado, THEN THE PluginRegistry SHALL lançar exceção com mensagem descritiva indicando o nome inválido e os provedores disponíveis

---

### Requirement 11: Interface de Ingestão (SMART_STITCH.MOD)

**User Story:** Como criador de conteúdo, quero revisar e ajustar os painéis detectados antes de prosseguir, para que eu tenha controle sobre o material que será processado.

#### Acceptance Criteria

1. WHEN o App está na tela SMART_STITCH.MOD, THE App SHALL exibir um viewer de páginas com scroll vertical e um grid de thumbnails 16:9 dos painéis detectados
2. WHEN o usuário seleciona um thumbnail no grid, THE App SHALL destacar o painel correspondente no viewer de páginas
3. WHEN o usuário reordena thumbnails por drag-and-drop no grid, THE App SHALL atualizar a ordem dos painéis que será enviada ao pipeline
4. WHEN o usuário clica em "Confirm", THE App SHALL transmitir o PanelSet confirmado ao PipelineOrchestrator via IPC e navegar para a tela Intelligence
5. WHILE a tela está no estado "loading", THE App SHALL exibir uma barra de progresso no header indicando o download/processamento das páginas

---

### Requirement 12: Interface de Processamento (Intelligence)

**User Story:** Como criador de conteúdo, quero acompanhar o progresso do processamento de IA em tempo real, para que eu saiba o status de cada tarefa e possa intervir se necessário.

#### Acceptance Criteria

1. WHEN a tela Intelligence está ativa, THE App SHALL exibir uma barra de progresso individual para cada tarefa paralela (Script Generation, Voice Synthesis, Image Upscale) com percentual e nome do provider ativo
2. WHEN o PipelineOrchestrator emite eventos de progresso via IPC, THE App SHALL atualizar as barras de progresso em tempo real sem recarregar a tela
3. WHEN todas as tarefas concluem com sucesso, THE App SHALL habilitar o botão "Continue to Production"
4. WHEN o usuário clica em "Cancel" durante o processamento, THE App SHALL enviar comando de cancelamento ao PipelineOrchestrator via IPC e retornar ao estado idle

---

### Requirement 13: Interface de Produção (TIMELINE_EDITOR)

**User Story:** Como criador de conteúdo, quero revisar a timeline montada e exportar o vídeo final, para que eu possa verificar o resultado antes de publicar.

#### Acceptance Criteria

1. WHEN a tela TIMELINE_EDITOR está ativa com uma Timeline montada, THE App SHALL exibir trilhas VIDEO, AUDIO e SUBS com os clipes correspondentes
2. WHEN o usuário arrasta o playhead na timeline, THE App SHALL atualizar o preview de vídeo para o frame correspondente ao timecode selecionado
3. WHEN o usuário clica em "EXPORT .OTIOZ", THE App SHALL abrir um modal de exportação com opções de formato (MP4, .OTIOZ, ambos) e opção de upload para YouTube
4. WHILE a exportação está em progresso, THE App SHALL exibir um modal com barra de progresso do FFmpeg
5. WHEN a exportação conclui com sucesso, THE App SHALL exibir um modal de sucesso com o path do arquivo exportado e, se aplicável, a URL do YouTube

---

### Requirement 14: Segurança e Credenciais

**User Story:** Como criador de conteúdo, quero que minhas credenciais de API sejam armazenadas com segurança, para que não haja risco de exposição acidental.

#### Acceptance Criteria

1. THE App SHALL armazenar API keys e credenciais exclusivamente em variáveis de ambiente ou arquivo `.env`, nunca em checkpoints ou logs
2. THE App SHALL armazenar tokens OAuth do YouTube em arquivo com permissões restritas (modo 600 no sistema de arquivos)
3. IF um path de arquivo fornecido pelo usuário contém sequências de path traversal, THEN THE App SHALL rejeitar o input e exibir mensagem de erro sem acessar o sistema de arquivos
4. THE App SHALL respeitar os rate limits de todos os provedores de API implementando exponential backoff para evitar banimento

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

---

### Property 1: Checkpoint round-trip

*For any* job_id, phase name, and serializable data object, saving a checkpoint and then loading it should produce an object equivalent to the original.

**Validates: Requirements 2.1, 2.2**

---

### Property 2: Retomada sem reprocessamento

*For any* pipeline job onde a fase Ingestion foi concluída com checkpoint salvo, retomar o job deve pular a fase Ingestion e executar apenas as fases restantes.

**Validates: Requirements 1.5, 2.2**

---

### Property 3: Checkpoints não contêm credenciais

*For any* checkpoint salvo pelo StateManager, o conteúdo serializado não deve conter strings que correspondam ao padrão de API keys ou tokens OAuth presentes na PipelineConfig.

**Validates: Requirements 2.5, 14.1**

---

### Property 4: Upload local preserva quantidade de páginas

*For any* lista não-vazia de paths de arquivos de imagem válidos, o PageDownloader deve retornar uma lista de PageImages com exatamente o mesmo número de elementos.

**Validates: Requirements 3.3**

---

### Property 5: Painéis detectados são não-sobrepostos

*For any* PageImage válida, os BoundingBoxes retornados pelo PanelDetector não devem ter sobreposição entre si (interseção de área zero).

**Validates: Requirements 4.1**

---

### Property 6: Painéis detectados estão em ordem de leitura

*For any* PageImage válida com múltiplos painéis, os BoundingBoxes retornados pelo PanelDetector devem estar ordenados por (y, x) — de cima para baixo, esquerda para direita.

**Validates: Requirements 4.2**

---

### Property 7: BubbleSeparator preserva cobertura do bbox

*For any* Panel detectado, a união de art_region e bubble_regions deve cobrir toda a área do bbox original do painel.

**Validates: Requirements 4.3**

---

### Property 8: SmartCropper produz aspect ratio 16:9

*For any* Panel válido, o CroppedPanel retornado pelo SmartCropper deve ter aspect ratio 16:9 com tolerância de ±1 pixel, sem distorção do conteúdo.

**Validates: Requirements 4.4, 4.5**

---

### Property 9: Script tem um segmento por painel

*For any* PanelSet não-vazio, o Script retornado pelo ScriptGenerator deve ter exatamente len(panels) ScriptSegments, todos com narration não-vazia.

**Validates: Requirements 5.1, 5.2**

---

### Property 10: Áudio tem um segmento por ScriptSegment

*For any* Script válido, a lista de AudioSegments retornada pelo VoiceGenerator deve ter exatamente len(script.segments) elementos, todos em formato WAV 44.1kHz.

**Validates: Requirements 6.1, 6.3**

---

### Property 11: Duração do áudio respeita duration_hint

*For any* ScriptSegment com duration_hint > 0, a duração do AudioSegment sintetizado deve estar dentro do intervalo [duration_hint × 0.8, duration_hint × 1.2].

**Validates: Requirements 6.2**

---

### Property 12: UpscaledImage tem resolução mínima

*For any* CroppedPanel válido, a UpscaledImage retornada pelo ImageUpscaler deve ter largura ≥ 1920 e altura ≥ 1080 pixels.

**Validates: Requirements 7.1**

---

### Property 13: Timeline tem um clipe por painel

*For any* conjunto de UpscaledImages, AudioSegments e Script com o mesmo número de elementos, a Timeline retornada pelo TimelineAssembler deve ter exatamente len(panels) TimelineClips.

**Validates: Requirements 8.1**

---

### Property 14: Clipes da timeline não se sobrepõem

*For any* Timeline montada, nenhum par de TimelineClips deve ter sobreposição temporal (o end_time de um clipe deve ser ≤ ao start_time do próximo).

**Validates: Requirements 8.2**

---

### Property 15: Duração total da timeline é consistente

*For any* Timeline montada, total_duration deve ser igual à soma das durações de todos os AudioSegments utilizados na montagem.

**Validates: Requirements 8.3**

---

### Property 16: Ken Burns zoom permanece no intervalo configurado

*For any* KenBurnsParams válido com 1.0 ≤ start_zoom ≤ end_zoom ≤ 2.0, o valor de zoom calculado para cada frame deve estar dentro do intervalo [start_zoom, end_zoom].

**Validates: Requirements 8.4, 8.5**

---

### Property 17: Path traversal é rejeitado

*For any* string de path que contenha a sequência `../` ou `..\\`, o PageDownloader deve rejeitar o input e retornar erro de validação sem realizar nenhum acesso ao sistema de arquivos.

**Validates: Requirements 3.4, 14.3**
