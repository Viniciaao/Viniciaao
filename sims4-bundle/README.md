# The Sims 4 – 5 sims mais recentes do CurseForge + todos os CCs (TUDO JUNTO)

Pedido: baixar os **5 sims mais recentes** de
<https://www.curseforge.com/sims4/search?class=sims-households&page=1&pageSize=20&sortBy=creation+date>,
descobrir **todos os mods/CC** que cada um usa, baixar um por um e **juntar tudo em um único download**.

## Os 5 sims (ordem de criação, 06/09/2026)

| # | Sim | Criador | Página | Arquivo |
|---|-----|---------|--------|---------|
| 1 | Edith Medina | miwisimsie | <https://www.curseforge.com/sims4/sims-households/edith-medina> | `Miwisimsie_Edith Medina.zip` |
| 2 | Luciana Neal | miwisimsie | <https://www.curseforge.com/sims4/sims-households/luciana-neal> | `Miwisimsie_Luciana Neal.zip` |
| 3 | Serena Slade | miwisimsie | <https://www.curseforge.com/sims4/sims-households/serena-slade> | `Miwisimsie_Serena Slade.zip` |
| 4 | Uminunu-F12 The Sweet Streamer | Uminunu | <https://www.curseforge.com/sims4/sims-households/uminunu-f12-the-sweet-streamer> | `Uminunu-F12-The Sweet Streamer.zip` |
| 5 | Rosemary Haney | daboosims | <https://www.curseforge.com/sims4/sims-households/rosemary-haney> | `Daboosims Rosemary Haney.zip` |

Cada página lista o CC obrigatório (maquiagem, pele, cabelo, roupas, sliders…). São ~40 itens por sim,
vindos de **The Sims Resource**, **Patreon**, **CurseForge**, ModTheSims, Tumblr, etc. — no total ~150 CCs únicos.

## Onde está o download "TUDO JUNTO"

O sandbox deste agente **não tem acesso de rede** ao CurseForge/TSR/Patreon (apenas GitHub), então o
download real roda no **GitHub Actions** (`.github/workflows/sims4-download.yml`), que:

1. Baixa o arquivo de cada sim (tray) do CurseForge.
2. Lê a descrição de cada sim e baixa **cada CC** (TSR com ticket/espera, Patreon via API pública, CurseForge via CDN, Google Drive, SimFileShare, Dropbox, MediaFire, ModTheSims, páginas de blog/tumblr).
3. Extrai tudo (zip/rar/7z, inclusive zip dentro de zip) e organiza:
   - `Tray/` → arquivos `.trayitem`, `.householdbinary`, `.hhi`, `.sgi`…
   - `Mods/<nome do CC>/` → `.package`
4. Gera `TUDO_JUNTO_Sims4.zip` (dividido em partes de ~1,75 GB só se precisar) e publica na **Release**:

   **➡️ <https://github.com/Viniciaao/Viniciaao/releases/tag/sims4-tudo-junto>**

   Também commita em `sims4-bundle/pacote/`: `relatorio.md` (tabela sim → CC → status → arquivo),
   `relatorio.json`, `resumo.md`, `log.txt`, `TAMANHO.txt` e uma cópia do zip se tiver ≤ 95 MB.

## Como instalar

1. Extraia o zip (se houver várias partes, extraia **todas** na mesma pasta).
2. `Tray/*` → `Documentos\Electronic Arts\The Sims 4\Tray`
3. `Mods/*` → `Documentos\Electronic Arts\The Sims 4\Mods`
4. No jogo: Opções → Outros → ativar *Conteúdo personalizado e mods* → reiniciar.
5. Galeria → Minha Biblioteca → marcar *Incluir conteúdo personalizado* → procurar o nome do sim.

## O que pode faltar

- **Patreon exclusivo de assinantes** (early access pago): a API pública não entrega o arquivo. O relatório
  lista o link para você baixar logado. Muitos posts ficam grátis depois do período de early access.
- **TSR "VIP Early Access"**: mesma coisa, link fica no relatório.
- **MEGA / pastas do Google Drive**: precisam de download manual (link no relatório).

## Rodar de novo

Basta alterar `sims4-bundle/.trigger` (ou usar *Run workflow* na aba Actions) que o pipeline refaz tudo e
atualiza a Release.
