# Cartone animato per bambini con ComfyUI su T4 gratuita

Stesso sistema di `D:\Colab_comfy`: ComfyUI gira su Colab o Kaggle (GPU T4 gratis),
sul PC c'è solo Python, che manda i prompt e scarica le immagini.
Modello: **Z-Image Turbo** (8 passi, ~20-40 s a immagine su T4).

## Struttura
```
Cartone_comfy/
├── comfyui_t4.ipynb            notebook Colab  (runtime T4)
├── comfyui_kaggle.ipynb        notebook Kaggle (~30 ore T4/settimana)
├── genera.py                   manda i prompt a ComfyUI e scarica i risultati
├── prepara_personaggi.py       schede personaggi -> prompt_personaggi.txt
├── prompt_personaggi.txt       generato, non modificatelo a mano
├── workflows/
│   ├── zimage_turbo_t2i.json       testo -> immagine
│   └── zimage_turbo_img2img.json   immagine -> immagine (denoise 0.45)
├── personaggi/
│   ├── stile.txt               stile grafico comune a tutto il cartone
│   ├── _modello/scheda.txt     modello da copiare per ogni personaggio
│   ├── Tina/scheda.txt         esempio (tartarughina)
│   └── Lumo/scheda.txt         esempio (lucciola)
├── luoghi/                     (prossimo passo) sfondi e ambientazioni
├── episodi/                    (prossimo passo) bibbia della serie, storie, storyboard
└── output/                     immagini scaricate (non versionate)
```

## Avvio ComfyUI
1. Aprite `comfyui_t4.ipynb` su Colab (Runtime → Cambia tipo di runtime → **T4 GPU**)
   oppure `comfyui_kaggle.ipynb` su Kaggle (Accelerator **GPU T4 x2**, Internet **On**).
2. Eseguite le celle in ordine: la cella dei modelli scarica già Z-Image Turbo.
3. Copiate il link `https://xxxx.trycloudflare.com` dell'ultima cella.

## Creare i personaggi

La difficoltà di un cartone è che **ogni personaggio deve restare identico** in tutte
le immagini. Il metodo è in due fasi.

### 0. Stile e schede
- `personaggi/stile.txt`: lo stile grafico, uguale per tutti. Decidetelo **prima** e poi
  non toccatelo più.
- Per ogni personaggio copiate `personaggi/_modello` in `personaggi/<Nome>` e compilate
  `scheda.txt`. I campi in inglese (`descrizione`, `abiti`, `segni`, `taglia`, `pose`)
  finiscono nei prompt; `carattere` e `voce` servono solo a voi.
- Consigli per le descrizioni: forme semplici, 2-3 colori dominanti per personaggio,
  un dettaglio unico (`segni`), colori diversi tra un personaggio e l'altro. Più la
  descrizione è precisa, più il personaggio resta uguale.

### 1. Concept: scegliere l'aspetto
```
python prepara_personaggi.py
python genera.py https://xxxx.trycloudflare.com --output output/Personaggi
```
Senza `--salta-fatte` lo script gira all'infinito e alterna i personaggi, facendo
tante proposte diverse in `output/Personaggi/<Nome>/1_concept_*.png`.
Fermatelo con Ctrl+C quando ne avete abbastanza.

Se nessuna proposta va bene, correggete la `descrizione` nella scheda, rilanciate
`prepara_personaggi.py` (genera.py rilegge il file dei prompt a ogni giro, non serve
fermarlo).

Quando una vi piace:
1. copiatela in `personaggi/<Nome>/riferimento.png`;
2. (facoltativo) scrivete nella scheda `seed:` il numero alla fine del nome del file
   (`1_concept_20261115_191200_`**`123456789`**`.png`).

### 2. Fogli del personaggio
Rilanciate `python prepara_personaggi.py`: per chi ha il `riferimento.png` ora prepara

| Immagine | Cosa contiene | Dimensioni |
|---|---|---|
| `2_turnaround` | fronte, 3/4, lato, retro nella stessa immagine | 1536x768 |
| `3_espressioni` | felice, triste, sorpreso, arrabbiato, spaventato, ride | 1248x832 |
| `4_posa_*` | una per ogni posa della scheda | 1024x1024 |
| `5_variante` | img2img dal riferimento: stesso personaggio, piccole differenze | 1024x1024 |
| `Gruppo/insieme` | tutti i personaggi insieme, per controllare altezze e colori | 1536x864 |

```
python genera.py https://xxxx.trycloudflare.com --output output/Personaggi
```
- Con `--salta-fatte` fa una sola immagine per riga e si ferma (utile se avete messo
  il `seed`, perché con lo stesso seed uscirebbe sempre la stessa immagine).
- Turnaround ed espressioni sono **in un'unica immagine** apposta: dentro la stessa
  immagine il modello mantiene il personaggio molto più coerente che tra immagini
  separate.
- `5_variante` usa `workflows/zimage_turbo_img2img.json`: `denoise` 0.45. Più basso =
  più fedele al riferimento, più alto = più libertà.

Le immagini migliori di ogni personaggio salvatele in `personaggi/<Nome>/`
(es. `turnaround.png`, `espressioni.png`, `posa_saluta.png`): sono il "model sheet"
ufficiale del personaggio e serviranno nelle fasi successive.

### Opzioni utili
```
python prepara_personaggi.py --solo Tina              solo un personaggio
python prepara_personaggi.py --fasi concept           rifà i concept anche se c'è il riferimento
python prepara_personaggi.py --fasi pose,espressioni  solo alcune fasi
python genera.py URL --quante 20                      si ferma dopo 20 immagini
```
Fasi disponibili: `concept, turnaround, espressioni, pose, varianti, gruppo`.

### Se i personaggi non restano abbastanza uguali
Il prompt fisso + il seed + i fogli in un'unica immagine bastano per il model sheet,
ma per le scene del cartone (personaggio in mille pose diverse) la soluzione
affidabile è una **LoRA** per ogni personaggio, addestrata su 15-30 immagini scelte da
`personaggi/<Nome>/`. È il passo successivo da fare prima delle scene.

## Prossimi passi (non ancora pronti)
1. **Luoghi** (`luoghi/`): sfondi senza personaggi, stessa logica delle schede.
2. **Episodi** (`episodi/`): bibbia della serie, storie, storyboard (una immagine per
   inquadratura con personaggi + luogo).
3. **Animazione**: image-to-video dalle inquadrature (es. Wan 2.x, pochi secondi a clip;
   su T4 è lento, si lavora a bassa risoluzione).
4. **Voci e montaggio**: sintesi vocale per i dialoghi, montaggio con ffmpeg o DaVinci.

## Storie (immagini + video)

Una storia è una cartella in `storie/` con `personaggi.txt`, `stile.txt`, `scene.txt`
(un blocco per inquadratura: immagine, movimento, narrazione, battute) e `storia.md`
(il racconto). Esempio: `storie/DaniTeo`.

### Una volta sola sul PC
```
scoop install ffmpeg
pip install kokoro-onnx soundfile
```
e in `modelli/kokoro/` i due file di Kokoro (voce italiana, offline):
`kokoro-v1.0.onnx` e `voices-v1.0.bin` da
https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0

### I passi
```
# 1. immagini (Z-Image Turbo)
python prepara_storia.py storie/DaniTeo
python genera.py URL --prompt-file storie/DaniTeo/prompt_storia.txt --salta-fatte

# 2. (facoltativo) copiate le immagini migliori in storie/DaniTeo/scelte/<id>.png

# 3. clip animate (Wan 2.2 5B, ~4 s a clip, alcuni minuti l'una su T4)
python prepara_storia.py storie/DaniTeo --video
python genera.py URL --prompt-file storie/DaniTeo/prompt_video.txt --workflow-immagine workflows/wan22_5b_i2v.json --salta-fatte

# 4. voce (Kokoro, sul PC)
python voce.py storie/DaniTeo

# 5. montaggio
python monta_video.py storie/DaniTeo --musica canzone.mp3 --sottotitoli-nel-video
```
`monta_video.py` usa per ogni scena la clip animata se c'è, altrimenti l'immagine con
uno zoom lento; la voce di `storie/<Storia>/voce/`; la durata segue la voce.
Le voci dei personaggi si cambiano in `VOCI` dentro `voce.py`.

### Clip in alta qualità su TPU (alternativa a ComfyUI, sperimentale)
Il notebook `wan_tpu_kaggle.ipynb` usa la TPU gratuita di Kaggle con
[MaxDiffusion](https://github.com/AI-Hypercomputer/maxdiffusion) e **Wan 2.2 I2V A14B** (il modello
grande) a 1280x720, al posto del passo 3:
```
python prepara_storia.py storie/DaniTeo --tpu     # crea storie/DaniTeo/kaggle_tpu/
```
1. caricate il contenuto di `kaggle_tpu/` come dataset Kaggle;
2. aprite `wan_tpu_kaggle.ipynb` su Kaggle con Accelerator **TPU**, Internet **On** e il dataset come input;
3. prima `PROVA = True` (una scena), poi `PROVA = False` con *Save & Run All (Commit)*;
4. estraete `clip_tpu.zip` in `output/DaniTeo_video/` e rifate il passo 5.
