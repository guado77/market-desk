# Market Desk

Cruscotto pubblico (GitHub Pages) di **Andrea Venturini** con gli ultimi output dei wrap di mercato.

**Sito:** https://guado77.github.io/market-desk/

> Solo a scopo informativo. Non è consulenza finanziaria né raccomandazione di investimento.
> I contenuti di terzi (Federal Reserve, BIS, IMF, Bloomberg, S&P Global) appartengono alle fonti citate.

## Come funziona

- `scripts/sync_wraps.py` legge i repo privati dei wrap e copia **solo** gli ultimi file di output
  (`.png`, `.pdf`, `.xlsx`, al massimo pochi per wrap) in `assets/<wrap>/`, poi rigenera `manifest.json`.
  Non copia mai codice, `state/`, `.env`, configurazioni, log o testi di chat/email.
- `index.html` legge `manifest.json` e mostra una sezione per wrap (immagine più recente, link a PDF/Excel,
  ora dell'ultimo aggiornamento in ora di Roma). Le sezioni senza file mostrano *In attesa del prossimo output*
  e si riempiono da sole quando le pipeline ripartono.
- `scripts/check_publish.py` blocca il commit se in `assets/` ci sono nomi non validi su Windows,
  estensioni non ammesse o testo che somiglia a un segreto.
- `.github/workflows/sync.yml` (da attivare, vedi sotto: oggi è in `setup/sync.yml`) gira ogni 2 ore, a mano (*Run workflow*) e su `repository_dispatch`
  (tipo `wrap-updated`), e committa le novità. Pages pubblica il branch `main` (cartella radice).

### Cosa NON viene pubblicato

| Repo | Motivo |
|---|---|
| `chat-wrap` | riassunti di conversazioni private di un gruppo Telegram |
| `gmail-wrap` | generato da email personali: sezione «Non pubblicato (contenuto privato)» |
| `bloomberg-wrap` (PDF) | copyright Bloomberg: nel sito solo titolo e data; i PDF vanno nel repo **privato** |
| `imf-spglobal-wrap_/articoli/spg` (PDF) | copyright S&P Global: come sopra |
| `desk` PDF «wrap-private» | edizione per il canale privato: si pubblica solo la card pubblica |

I PDF Bloomberg e S&P finiscono in **guado77/market-desk-private** (privato). Nel sito pubblico i link
«PDF nel repo privato 🔒» funzionano solo se sei collegato a GitHub come `guado77`.

## Attivare il workflow (una volta, a mano)

Il file del workflow è in `setup/sync.yml`: GitHub non permette di creare workflow con il token usato per
il primo caricamento (manca il permesso `workflow`). Per attivarlo:

1. Apri `setup/sync.yml` su GitHub → icona **Copy raw file**.
2. Nella pagina del repo: **Add file** → **Create new file** → nome `.github/workflows/sync.yml` → incolla →
   **Commit changes** sul branch `main`.
3. (Facoltativo) cancella `setup/sync.yml`.

In alternativa, dal box: `gh auth refresh -h github.com -s workflow` (conferma nel browser) e poi
`git mv setup/sync.yml .github/workflows/sync.yml && git commit && git push`.

## Token (da fare una volta, a mano)

Il workflow usa due secret. **Nessun token è salvato nel codice**; se `WRAPS_READ_TOKEN` manca, il
workflow si ferma subito con il messaggio *«Secret WRAPS_READ_TOKEN mancante: sincronizzazione saltata»*.

Servono due token perché un token fine-grained ha gli stessi permessi su tutti i repo selezionati:
con uno solo, chi scrive sul repo privato potrebbe scrivere anche sui wrap.

### 1. `WRAPS_READ_TOKEN` — sola lettura sui wrap

1. GitHub → foto profilo → **Settings** → **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token**.
2. *Token name*: `market-desk-read` · *Expiration*: 90 giorni (o 1 anno) · *Resource owner*: `guado77`.
3. *Repository access*: **Only select repositories** e scegli:
   `market-wrap`, `desk`, `tvol-wrap`, `fi-wrap`, `ice-evening-wrap`, `pun-wrap`, `basis-trade-wrap`,
   `macro-wrap-bot`, `oil-wrap`, `spr-monitor`, `wrap-monitor`, `Blas-Weekly-Wrap`, `hicp-wrap`,
   `FED-Wrap`, `Bis-Wrap`, `imf-spglobal-wrap_`, `bloomberg-wrap`.
   (Non servono `chat-wrap` e `gmail-wrap`.)
4. *Permissions → Repository permissions*:
   - **Contents: Read-only** (file nei repo)
   - **Actions: Read-only** (output salvati come *artifact* dei workflow: market-wrap, pun-wrap, spr-monitor, hicp-wrap, fi-wrap, Fed/BIS/IMF wrap)
   - *Metadata: Read-only* viene aggiunto da solo. Nient'altro.
5. **Generate token** e copialo (si vede una volta sola).
6. Repo **guado77/market-desk** → **Settings** → **Secrets and variables** → **Actions** →
   **New repository secret** → *Name*: `WRAPS_READ_TOKEN` → incolla → **Add secret**.

### 2. `PRIVATE_MIRROR_TOKEN` — scrittura solo sul repo privato (facoltativo)

Serve solo per copiare i PDF Bloomberg/S&P in `guado77/market-desk-private`. Senza, il sito mostra
comunque i titoli.

1. Come sopra, nuovo fine-grained token `market-desk-private-write`, *Resource owner* `guado77`.
2. *Repository access*: **Only select repositories** → solo `market-desk-private`.
3. *Permissions*: **Contents: Read and write** (Metadata read-only automatico). Nient'altro.
4. Aggiungilo in **guado77/market-desk** → Settings → Secrets and variables → Actions come
   `PRIVATE_MIRROR_TOKEN`.

### 3. Prova

Tab **Actions** → *Sync wrap outputs* → **Run workflow**. Alla scadenza dei token rigenerali
(*Regenerate token*) e aggiorna i due secret.

### Aggiornamento immediato da un wrap (facoltativo)

Un wrap può chiedere la sincronizzazione appena ha finito con una chiamata `repository_dispatch`
(tipo `wrap-updated`) verso `guado77/market-desk`; serve un token con *Contents: Read and write* su
`market-desk`. Senza questo passo il sito si aggiorna comunque entro 2 ore.

## Uso locale

```bash
WRAPS_READ_TOKEN=... python3 scripts/sync_wraps.py          # aggiorna assets/ e manifest.json
MIRROR_DIR=../market-desk-private WRAPS_READ_TOKEN=... python3 scripts/sync_wraps.py
python3 scripts/check_publish.py assets manifest.json
```

Le sezioni si configurano in cima a `scripts/sync_wraps.py` (lista `SECTIONS`: cartelle, artifact,
quanti file tenere). Le dimensioni del repo crescono con i nuovi output: se un giorno servisse,
si può passare al deploy di Pages via Actions senza committare `assets/`.
