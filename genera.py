"""Genera immagini (e in futuro video) in continuo con ComfyUI su Colab.

ComfyUI gira su Colab (notebook comfyui_t4.ipynb, cella 6). Questo script gira
sul PC: manda a ComfyUI un prompt alla volta, aspetta il risultato e lo scarica
in una cartella locale. Poi passa al prompt successivo, all'infinito.

Uso:
    python genera.py https://xxxx.trycloudflare.com

Opzioni utili:
    --prompt-file prompt.txt          un prompt per riga (righe con # ignorate);
                                      "Nome | prompt" usa Nome per il file;
                                      "Nome | prompt | 832x1248 | foto.jpg" fissa
                                      le dimensioni e parte da una foto (img2img);
                                      "... | seed=1234" usa sempre quel seed
    --workflow workflows/zimage_turbo_t2i.json
    --output "G:/Il mio Drive/ComfyUI_output"   (cartella di Drive per desktop)
    --workflow-immagine workflows/zimage_turbo_img2img.json
                                      usato per le righe con una foto di riferimento
    --quante 50                       si ferma dopo 50 generazioni (0 = mai)

Il file dei prompt viene riletto a ogni giro: potete modificarlo mentre lo
script gira. Per fermare lo script premete Ctrl+C.

Mentre lo script gira, su Windows il PC non va in sospensione (lo schermo può
spegnersi o bloccarsi). Quando lo script finisce torna tutto come prima.

Il workflow è un file JSON in formato API di ComfyUI. Il testo __PROMPT__ viene
sostituito con il prompt, e ogni ingresso 'seed' o 'noise_seed' riceve un seed
casuale. Così basta cambiare workflow per passare dalle immagini ai video.
"""

import argparse
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
SEGNAPOSTO = '__PROMPT__'
ATTESA_MAX_RETE = 300  # secondi di errori di rete prima di arrendersi


def impedisci_sospensione(attiva):
    """Su Windows chiede di non andare in sospensione finché lo script gira."""
    if sys.platform != 'win32':
        return
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    stato = ES_CONTINUOUS | ES_SYSTEM_REQUIRED if attiva else ES_CONTINUOUS
    ctypes.windll.kernel32.SetThreadExecutionState(stato)


def chiama(base, percorso, dati=None, timeout=60):
    """Richiesta HTTP verso ComfyUI. Restituisce i byte della risposta."""
    corpo = json.dumps(dati).encode('utf-8') if dati is not None else None
    richiesta = urllib.request.Request(
        base + percorso,
        data=corpo,
        headers={'Content-Type': 'application/json',
                 'User-Agent': 'genera-comfyui/1.0'},
    )
    with urllib.request.urlopen(richiesta, timeout=timeout) as risposta:
        return risposta.read()


def con_riprova(funzione, *args, **kwargs):
    """Ripete la chiamata se la rete cade, per al massimo ATTESA_MAX_RETE secondi."""
    inizio = time.time()
    while True:
        try:
            return funzione(*args, **kwargs)
        except urllib.error.HTTPError as e:
            # 502/503/504 arrivano dal tunnel Cloudflare (Colab irraggiungibile
            # per un momento): si riprova come per la rete. Gli altri codici
            # sono risposte vere di ComfyUI.
            if e.code not in (502, 503, 504):
                raise
            if time.time() - inizio > ATTESA_MAX_RETE:
                sys.exit(
                    f'\nIl link risponde {e.code} da {ATTESA_MAX_RETE // 60} minuti.\n'
                    'Forse la sessione Colab è finita: rieseguite la cella 6 e '
                    'rilanciate lo script con il nuovo link.')
            print(f'  il tunnel risponde {e.code}, riprovo tra 10 secondi...')
            time.sleep(10)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if time.time() - inizio > ATTESA_MAX_RETE:
                sys.exit(
                    f'\nComfyUI non risponde da {ATTESA_MAX_RETE // 60} minuti ({e}).\n'
                    'Forse la sessione Colab è finita: rieseguite la cella 6 e '
                    'rilanciate lo script con il nuovo link.')
            print(f'  rete non disponibile ({e}), riprovo tra 10 secondi...')
            time.sleep(10)


def leggi_prompt(file):
    righe = file.read_text(encoding='utf-8').splitlines()
    return [r.strip() for r in righe if r.strip() and not r.strip().startswith('#')]


def prepara_workflow(modello, prompt, seed, larghezza=1024, altezza=1024, immagine=None):
    # Sostituisce __PROMPT__ ovunque compaia, con l'escape JSON corretto.
    testo = json.dumps(modello).replace(SEGNAPOSTO, json.dumps(prompt)[1:-1])
    workflow = json.loads(testo)
    valori = {'__WIDTH__': larghezza, '__HEIGHT__': altezza, '__IMAGE__': immagine}
    for nodo in workflow.values():
        ingressi = nodo.get('inputs', {})
        for chiave in ('seed', 'noise_seed'):
            if chiave in ingressi and not isinstance(ingressi[chiave], list):
                ingressi[chiave] = seed
        for chiave, valore in ingressi.items():
            if isinstance(valore, str) and valore in valori:
                ingressi[chiave] = valori[valore]
    return workflow


def carica_immagine(base, percorso):
    """Manda una foto di riferimento a ComfyUI (cartella input) e ne restituisce il nome."""
    nome = 'rif_' + nome_breve(percorso.stem, 80) + percorso.suffix.lower()
    confine = uuid.uuid4().hex
    corpo = (
        f'--{confine}\r\nContent-Disposition: form-data; name="image"; filename="{nome}"\r\n'
        'Content-Type: application/octet-stream\r\n\r\n').encode() + percorso.read_bytes() + (
        f'\r\n--{confine}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue'
        f'\r\n--{confine}--\r\n').encode()
    richiesta = urllib.request.Request(
        base + '/upload/image', data=corpo,
        headers={'Content-Type': f'multipart/form-data; boundary={confine}',
                 'User-Agent': 'genera-comfyui/1.0'})
    with urllib.request.urlopen(richiesta, timeout=300) as risposta:
        info = json.loads(risposta.read())
    return f"{info['subfolder']}/{info['name']}" if info.get('subfolder') else info['name']


def aspetta_risultato(base, prompt_id):
    """Aspetta che ComfyUI finisca e restituisce la voce della cronologia."""
    while True:
        storia = json.loads(con_riprova(chiama, base, f'/history/{prompt_id}'))
        if prompt_id in storia:
            return storia[prompt_id]
        time.sleep(2)


def file_prodotti(voce):
    """Elenca i file finali (immagini, gif, video) prodotti dal workflow."""
    for uscita in voce.get('outputs', {}).values():
        for elenco in uscita.values():
            if not isinstance(elenco, list):
                continue
            for f in elenco:
                if isinstance(f, dict) and 'filename' in f and f.get('type', 'output') == 'output':
                    yield f


def nome_breve(testo, lunghezza=40):
    return re.sub(r'[^a-zA-Z0-9]+', '_', testo).strip('_')[:lunghezza] or 'prompt'


def dividi_riga(riga):
    """'Nome | prompt | 832x1248 | foto.jpg' -> (nome, prompt, opzioni).

    Senza '|' il nome è il prompt stesso. I campi dopo il prompt sono facoltativi:
    'LxA' fissa le dimensioni, qualsiasi altro testo è il percorso di una foto di
    riferimento (in quel caso si usa il workflow img2img).
    """
    parti = [p.strip() for p in riga.split('|')]
    if len(parti) < 2 or not parti[1]:
        return riga, riga, {}
    opzioni = {}
    for extra in parti[2:]:
        dimensioni = re.fullmatch(r'(\d+)\s*x\s*(\d+)', extra)
        seed = re.fullmatch(r'seed\s*=\s*(\d+)', extra)
        if seed:
            opzioni['seed'] = int(seed.group(1))
        elif dimensioni:
            opzioni['larghezza'], opzioni['altezza'] = map(int, dimensioni.groups())
        elif extra:
            opzioni['immagine'] = Path(extra)
    return parti[0], parti[1], opzioni


def destinazione(output, nome):
    """'Frutto/Mango' -> (cartella output/Frutto, prefisso 'Mango')."""
    parti = [nome_breve(p) for p in nome.split('/') if p.strip()] or ['prompt']
    return output.joinpath(*parti[:-1]), parti[-1]


def gia_fatta(output, nome):
    cartella, prefisso = destinazione(output, nome)
    if not cartella.is_dir():
        return False
    schema = re.compile(re.escape(prefisso) + r'_\d{8}_\d{6}_')
    return any(schema.match(f.name) for f in cartella.iterdir())


def main():
    p = argparse.ArgumentParser(description='Generazione continua con ComfyUI su Colab.')
    p.add_argument('url', help='link trycloudflare.com stampato dalla cella 6')
    p.add_argument('--prompt-file', type=Path, default=CARTELLA / 'prompt_personaggi.txt')
    p.add_argument('--workflow', type=Path, default=CARTELLA / 'workflows' / 'zimage_turbo_t2i.json')
    p.add_argument('--workflow-immagine', type=Path,
                   default=CARTELLA / 'workflows' / 'zimage_turbo_img2img.json',
                   help='workflow img2img per le righe con una foto di riferimento '
                        '(deve contenere __IMAGE__)')
    p.add_argument('--output', type=Path, default=CARTELLA / 'output')
    p.add_argument('--quante', type=int, default=0, help='numero di generazioni (0 = infinite)')
    p.add_argument('--salta-fatte', action='store_true',
                   help="salta le righe che hanno già un'immagine nella cartella di output "
                        'e si ferma quando le ha fatte tutte (utile per riprendere)')
    args = p.parse_args()

    base = args.url.strip().rstrip('/')
    modello = json.loads(args.workflow.read_text(encoding='utf-8'))
    if SEGNAPOSTO not in json.dumps(modello):
        sys.exit(f'Nel workflow {args.workflow} manca il testo {SEGNAPOSTO}.')
    args.output.mkdir(parents=True, exist_ok=True)
    client_id = str(uuid.uuid4())
    modello_immagine = None  # caricato solo se serve
    caricate = {}  # foto di riferimento già mandate a ComfyUI in questa sessione

    print(f'ComfyUI:  {base}')
    print(f'Workflow: {args.workflow.name}')
    print(f'Salvo in: {args.output}')
    print('Ctrl+C per fermare.\n')

    fatte = 0
    fallite = set()  # con --salta-fatte non riprova all'infinito le righe in errore
    impedisci_sospensione(True)
    try:
        while args.quante == 0 or fatte < args.quante:
            righe = leggi_prompt(args.prompt_file)
            if not righe:
                sys.exit(f'Il file {args.prompt_file} non contiene prompt.')
            if args.salta_fatte:
                da_fare = [r for r in righe if r not in fallite
                           and not gia_fatta(args.output, dividi_riga(r)[0])]
                if not da_fare:
                    print('Tutte le righe hanno già la loro immagine. Finito.')
                    break
                riga = da_fare[0]
                print(f'(mancano {len(da_fare)})')
            else:
                riga = righe[fatte % len(righe)]
            # Riga nel formato "Nome | prompt": il nome serve per il file;
            # "Cartella/Nome" salva nella sottocartella.
            nome, prompt, opzioni = dividi_riga(riga)
            seed = opzioni.get('seed', random.randint(0, 2**32 - 1))
            print(f'[{fatte + 1}] {nome} - seed {seed}')

            foto = opzioni.get('immagine')
            nome_foto = None
            if foto:
                if modello_immagine is None:
                    modello_immagine = json.loads(args.workflow_immagine.read_text(encoding='utf-8'))
                    if '__IMAGE__' not in json.dumps(modello_immagine):
                        sys.exit(f'Nel workflow {args.workflow_immagine} manca il testo __IMAGE__.')
                if not foto.is_file():
                    print(f'  foto di riferimento non trovata: {foto}')
                    fallite.add(riga)
                    fatte += 1
                    continue
                if foto not in caricate:
                    print(f'  carico la foto {foto.name}')
                    caricate[foto] = con_riprova(carica_immagine, base, foto)
                nome_foto = caricate[foto]
            workflow = prepara_workflow(modello_immagine if foto else modello, prompt, seed,
                                        opzioni.get('larghezza', 1024),
                                        opzioni.get('altezza', 1024), nome_foto)
            try:
                risposta = con_riprova(chiama, base, '/prompt',
                                       {'prompt': workflow, 'client_id': client_id})
            except urllib.error.HTTPError as e:
                dettaglio = e.read().decode('utf-8', 'replace')
                sys.exit(f'ComfyUI ha rifiutato il workflow (errore {e.code}):\n{dettaglio}')
            prompt_id = json.loads(risposta)['prompt_id']

            inizio = time.time()
            voce = aspetta_risultato(base, prompt_id)
            stato = voce.get('status', {})
            if stato.get('status_str') == 'error':
                print('  errore durante la generazione:')
                for messaggio in stato.get('messages', []):
                    if messaggio[0] == 'execution_error':
                        print('   ', messaggio[1].get('exception_message', '').strip())
                fallite.add(riga)
                fatte += 1
                continue

            ora = datetime.now().strftime('%Y%m%d_%H%M%S')
            cartella, prefisso = destinazione(args.output, nome)
            cartella.mkdir(parents=True, exist_ok=True)
            for i, f in enumerate(file_prodotti(voce)):
                query = urllib.parse.urlencode({k: f.get(k, '') for k in ('filename', 'subfolder', 'type')})
                dati = con_riprova(chiama, base, f'/view?{query}', timeout=300)
                estensione = Path(f['filename']).suffix
                suffisso = f'_{i}' if i else ''
                dest = cartella / f'{prefisso}_{ora}_{seed}{suffisso}{estensione}'
                dest.write_bytes(dati)
                print(f'  salvato {dest.relative_to(args.output)} ({time.time() - inizio:.0f} s)')
            fatte += 1
    except KeyboardInterrupt:
        print(f'\nFermato. Generazioni completate: {fatte}.')
    finally:
        impedisci_sospensione(False)


if __name__ == '__main__':
    main()
