# Como compilar e instalar o mod — PQ "Eclipse do Deus Caído"

Este pacote é o **projeto-fonte `.x2qs`** da Missão Paralela customizada
**PQ "Eclipse do Deus Caído"** (identificador interno `TMQ_EVE_160`).

> **Por que não tem o `.x2m` pronto aqui?**
> O `.x2m` é um binário gerado por uma ferramenta **Windows** (o *XV2 Quest
> Creator*, da Eternity Tools). Este ambiente de trabalho é Linux e não consegue
> rodar essa ferramenta nem gerar o binário. Então entreguei o que a ferramenta
> consome: os 5 arquivos-fonte `.x2qs` prontos + este guia. São ~2 minutos de
> trabalho no seu PC para virar um `.x2m` instalável.

---

## 1. O que tem na pasta

```
mod/
├── COMO-COMPILAR.md          ← este guia
└── TMQ_EVE_160/              ← pasta do projeto da missão (aponte o Quest Creator aqui)
    ├── quest.x2qs            ← títulos + objeto Quest + recompensas (drops)
    ├── chars.x2qs            ← personagens (jogador, inimigos e aliado)
    ├── dialogue.x2qs         ← falas dos chefes (PT-BR + EN)
    ├── positions.x2qs        ← posições de spawn de cada área
    └── script.x2qs           ← roteiro da missão (ondas, portais, Ultimate Finish)
```

Tudo usa **apenas personagens, mapas e skills 100% vanilla** do jogo — não
depende de nenhum outro mod.

| Ato | Mapa (código) | Inimigos |
|---|---|---|
| 1 | Planeta Namek (`BFnmc`) | Appule + Raspberry → Dodoria + Zarbon → Freeza (1ª forma) |
| 2 | West City Subúrbios (`BFtwh`) | proteger Trunks: Ginyu + Recoome → Jeice + Burter |
| 3 | Arena dos Jogos de Cell (`BFcel`) | Androide 17 + 18 → Cell Perfeito → Cell Full Power |
| 4 | Planeta Sem Nome (`BFsmt`) | Beerus + Whis |
| 5 | Time Rift (`BFtok`) | Towa → Mira (Ki Divino) |
| ★ | Ultimate Finish | Mira — forma final (`MRN`), só se cumpriu os 2 segredos |

**Segredos do Ultimate Finish** (precisa dos **dois**):
1. Terminar o Ato 2 com **Trunks ≥ 80% de vida**;
2. No Ato 4, **derrotar Whis antes de Beerus**.

---

## 2. Pré-requisitos (só a primeira vez)

1. **Dragon Ball Xenoverse 2 (PC/Steam)** instalado e atualizado.
2. Baixar o **XV2 Mods Installer** (pacote da *Eternity Tools*) — ele já inclui
   o **XV2 Quest Creator** e os demais creators:
   - Site oficial / fórum: `https://animegamemods.freeforums.net/` (tópico
     "XV2 Mods Installer").
   - Link alternativo: `https://videogamemods.com/xenoverse/mods/xv2-mods-installer/`
3. (Opcional, para editar/depurar) o **XV2 Quest Importer**, que descompila
   missões vanilla para `.x2qs` de referência.

---

## 3. Gerando o `.x2m` (XV2 Quest Creator)

1. Abra o **XV2 Quest Creator** (vem no pacote do XV2 Mods Installer).
2. Na aba **Info**, preencha:
   - **Nome do mod**: `Eclipse do Deus Caído` (ou o que preferir);
   - **Autor**: seu nome;
   - **Versão**: `1.0`.
   - O **tipo da missão** é detectado automaticamente pelo prefixo `TMQ_`
     (Missão Paralela). Não mude o nome interno `TMQ_EVE_160`.
3. Na aba **Files**, aponte o **diretório da missão** para a pasta `TMQ_EVE_160`
   deste pacote (a que contém `quest.x2qs`, `chars.x2qs`, etc.).
4. Clique em **Save** / **Save as** e salve como `TMQ_EVE_160.x2m`.
   - Se aparecer algum erro de compilação, o log dirá o **arquivo** e a
     **linha** exatos — veja a seção 6 abaixo.

> Os arquivos precisam manter **exatamente** os nomes `quest.x2qs`,
> `chars.x2qs`, `dialogue.x2qs`, `positions.x2qs` e `script.x2qs`. O compilador
> lê nessa ordem.

---

## 4. Instalando (XV2 Mods Installer)

1. Feche o jogo (se estiver aberto).
2. Abra o **XV2 Mods Installer** e garanta que o **XV2 Patcher** está instalado
   (o instalador pede na primeira vez).
3. Vá em **Install** (ou arraste o `TMQ_EVE_160.x2m` para a janela) e escolha o
   arquivo `.x2m` que você gerou.
4. Aguarde a instalação terminar (o instalador compila os arquivos do jogo).
5. Abra o jogo. A missão aparece como uma nova **PQ de 6 estrelas** na lista de
   Missões Paralelas (a posição exata/número é atribuída pelo instalador — o
   "160" do título é só o nome fictício do design).

---

## 5. Solução de problemas

### "Cannot resolve skill ..." (drop de skill)
Os drops usam códigos de 3 letras do jogo:
`SKM` (Warp Kamehameha), `SGL` (Super Galick Gun), `SDK` (Spread Shot Retreat) e
`FNF` (Final Flash). Se o seu jogo/base não reconhecer algum (versão muito antiga
ou sem DLC), **remova aquela linha** `SkillReward { ... }` inteira no
`quest.x2qs` e recompile — o restante funciona normalmente.

### O "FAIL" aparece mas a missão é considerada concluída
Esta v1 **não usa falha por script** (falha só por derrota do time ou tempo).
Se você adicionar um evento com `QuestFinishState(FAIL)`, é preciso copiar os
blocos `QxdUnk1`/`QxdUnk2` de uma missão vanilla que falha por script (o
*Quest Importer* descompila essas missões). Por padrão deixei o fluxo sem esse
caso para evitar o bug conhecido de "FAIL que vira clear".

### Personagem não aparece / aparece no lugar errado
As posições usam `TRESPASS_0..2` e `TRESPASS_PLAYER_0..2` (pontos padrão dos
mapas). Se um inimigo "sumir", confira se o `stage` do `QmlChar` bate com o
`stage` do `CharaSpawn` correspondente no `script.x2qs` (o tutorial da Eternity
exige que ambos sejam iguais).

### Quero mudar o número de jogadores
Em `quest.x2qs`, mude `num_players` (1 a 3). Os 3 slots `Player`, `Player2`,
`Player3` em `chars.x2qs` já estão prontos para co-op.

---

## 6. Limitações desta versão (v1) vs. o design

O design completo está em `../PQ-160-Eclipse-do-Deus-Caido.md`. Para manter a
missão **instalável só com assets vanilla** e robusta, esta v1 simplifica:

| Design (documento) | Nesta v1 |
|---|---|
| 6 condições ocultas do Ultimate Finish | **2 condições** (Trunks ≥80% e Whis antes de Beerus) |
| Limite de tempo por ato (7/4/6/5/8 min) | Um cronômetro global de **30 min** |
| "Corrompidos" com +15% vida/+10% dano e aura roxa | Personagens vanilla normais (stats `-1` = padrão) |
| Skills novas ("Onda do Juízo Final", "Salto do Eclipse") | Drops de skills vanilla (SKM/SGL/SDK/FNF) |
| Falha por script (Trunks/máquina zerados) | Falha só por derrota/timeout |
| Ato 2 em "Conton City (cais do tempo)" | West City Subúrbios (Conton não é mapa de batalha) |
| Super Alma, equipamentos e arte como drops | Apenas drops de skill |

Tudo isso está documentado em comentários dentro dos `.x2qs` para você ajustar.

---

## 7. Como personalizar depois

- **Trocar um chefe**: edite o `char: "XXX"` do `QxdChar` em `chars.x2qs`
  (códigos de 3 letras do jogo: `FRZ`, `CL4`, `BLS`, `MIR`, etc.).
- **Mudar a vida/dano**: troque os `-1.0` por valores (ex.: `health: 1.5` =
  +50%). `-1.0` = usa o valor padrão do personagem.
- **Adicionar ondas**: copie um `Event` do `script.x2qs`, mude a condição
  `NumCharsDefeated(...)` e adicione `LoadChara(...)` + `CharaSpawn(...)`.
- **Editar textos**: altere os `TextEntry` (títulos no `quest.x2qs`, falas no
  `dialogue.x2qs`) — `en` é obrigatório, `pt` é o português.
- **Referências**: listas oficiais da Eternity — condições
  (`/thread/3084/list-x2qs-script-conditions`), ações
  (`/thread/3085/list-x2qs-script-actions`) e estágios
  (`/thread/2848/stages-list`) em `animegamemods.freeforums.net`.

Bom jogo! 🎮
