"""Crea il file dei prompt di una storia a partire dalle sue scene.

Una storia è una cartella (es. storie/DaniTeo) con dentro:
    personaggi.txt   "Nome: descrizione in inglese", una riga per personaggio
    stile.txt        stile grafico della storia (inglese)
    scene.txt        un blocco [id] per inquadratura (vedi il file per i campi)

Lo script scrive <cartella>/prompt_storia.txt nel formato di genera.py:

    <Storia>/<id> | prompt | LxA [| seed=N]

Con --video scrive invece <cartella>/prompt_video.txt: una riga per scena che anima
l'immagine scelta (scelte/<id>.png, altrimenti l'ultima generata) con il campo
"movimento:", da usare con il workflow workflows/wan22_5b_i2v.json.

Con --tpu prepara invece la cartella <cartella>/kaggle_tpu/ (immagini + clip.txt) da caricare
come dataset su Kaggle per il notebook wan_tpu_kaggle.ipynb (Wan 2.2 grande su TPU).

Uso:
    python prepara_storia.py storie/DaniTeo
    python prepara_storia.py storie/DaniTeo --solo 15_sguardo,16_si
    python prepara_storia.py storie/DaniTeo --video
    python prepara_storia.py storie/DaniTeo --tpu
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
FORMATO = '1536x864'  # 16:9, lo stesso del video finale
FORMATO_VIDEO = '832x480'  # Wan 2.2 5B su T4: multipli di 32, ~16:9
ESTENSIONI = ('.png', '.jpg', '.jpeg', '.webp')
SENZA_SCRITTE = 'No text, no letters, no words, no logos, no watermark, no frame, no border.'
VIDEO_FINALE = ('Smooth natural motion, the characters keep exactly the same faces, hair and '
                'clothes as in the image, consistent style.')


def righe_utili(file):
    return [r.strip() for r in file.read_text(encoding='utf-8').splitlines()
            if r.strip() and not r.strip().startswith('#')]


def leggi_personaggi(file):
    personaggi = {}
    for riga in righe_utili(file):
        if ':' in riga:
            nome, descrizione = riga.split(':', 1)
            personaggi[nome.strip()] = descrizione.strip()
    return personaggi


def leggi_scene(file):
    """Blocchi '[id]' seguiti da righe 'campo: valore' -> lista di dizionari.

    'parla: Nome | battuta' si può ripetere: diventa la lista scena['parla']
    di coppie (nome, battuta), nell'ordine.
    """
    scene = []
    for riga in righe_utili(file):
        intestazione = re.fullmatch(r'\[(.+)\]', riga)
        if intestazione:
            scene.append({'id': intestazione.group(1).strip(), 'parla': []})
        elif scene and ':' in riga:
            campo, valore = riga.split(':', 1)
            campo, valore = campo.strip().lower(), valore.strip()
            if campo == 'parla':
                chi, _, battuta = valore.partition('|')
                scene[-1]['parla'].append((chi.strip(), battuta.strip()))
            else:
                scene[-1][campo] = valore
    return scene


def trova_immagine(cartella, output, scena):
    """L'immagine scelta in <cartella>/scelte/<id>.*, altrimenti l'ultima generata."""
    for est in ESTENSIONI:
        scelta = cartella / 'scelte' / (scena + est)
        if scelta.is_file():
            return scelta
    generate = [f for f in (output / cartella.name).glob(f'{scena}_*.*')
                if f.suffix.lower() in ESTENSIONI]
    return max(generate, key=lambda f: f.stat().st_mtime) if generate else None


def componi_prompt(scena, personaggi, stile):
    testo = scena['immagine'].rstrip('. ')
    for nome, descrizione in personaggi.items():
        testo = testo.replace('{' + nome + '}', f'{nome}, {descrizione},')
    sconosciuti = re.findall(r'\{(\w+)\}', testo)
    if sconosciuti:
        sys.exit(f'Scena {scena["id"]}: personaggi non in personaggi.txt: {", ".join(sconosciuti)}')
    testo = re.sub(r',\s*([,.])', r'\1', testo)  # niente ",," dopo le descrizioni
    if scena.get('scritta'):
        finale = (f'The handwritten words "{scena["scritta"]}" written elegantly at the bottom '
                  'of the image. No other text, no logos, no watermark, no frame.')
    else:
        finale = SENZA_SCRITTE
    return f'{testo}. {stile} {finale}'


def prompt_video(scena, stile):
    return f'{scena["movimento"].rstrip(". ")}. {VIDEO_FINALE} {stile}'


def scrivi_tpu(cartella, scene, stile, solo, output):
    """Cartella kaggle_tpu/: un'immagine per scena (<id>.png) e clip.txt con "id | prompt"."""
    uscita = cartella / 'kaggle_tpu'
    if uscita.exists():
        shutil.rmtree(uscita)
    uscita.mkdir()
    righe = []
    for scena in scene:
        if solo and scena['id'] not in solo:
            continue
        foto = trova_immagine(cartella.resolve(), output.resolve(), scena['id'])
        if not foto or not scena.get('movimento'):
            print(f'  {scena["id"]}: niente immagine o "movimento:", salto')
            continue
        shutil.copy2(foto, uscita / f'{scena["id"]}{foto.suffix.lower()}')
        righe.append(f'{scena["id"]} | {prompt_video(scena, stile)}')
    (uscita / 'clip.txt').write_text('\n'.join(righe) + '\n', encoding='utf-8')
    print(f'Preparate {len(righe)} scene in {uscita}\n'
          'Caricate questa cartella come dataset su Kaggle (vedi wan_tpu_kaggle.ipynb).')


def scrivi_video(cartella, scene, stile, solo, output):
    """Una riga per scena: anima l'immagine scelta (o l'ultima generata) con Wan."""
    righe = []
    for scena in scene:
        if solo and scena['id'] not in solo:
            continue
        foto = trova_immagine(cartella.resolve(), output.resolve(), scena['id'])
        if not foto:
            print(f'  {scena["id"]}: nessuna immagine, salto (generate prima le immagini)')
            continue
        if not scena.get('movimento'):
            print(f'  {scena["id"]}: manca "movimento:", salto')
            continue
        prompt = prompt_video(scena, stile)
        righe.append(f'{cartella.name}_video/{scena["id"]} | {prompt} | {FORMATO_VIDEO} | '
                     f'{foto.as_posix()}')
    uscita = cartella / 'prompt_video.txt'
    intestazione = ['# Generato da prepara_storia.py --video: non modificatelo a mano.',
                    '# Usatelo con: --workflow-immagine workflows/wan22_5b_i2v.json']
    uscita.write_text('\n'.join(intestazione + righe) + '\n', encoding='utf-8')
    print(f'Scritte {len(righe)} clip in {uscita}')


def main():
    a = argparse.ArgumentParser(description='Crea prompt_storia.txt dalle scene di una storia.')
    a.add_argument('cartella', type=Path, help='cartella della storia, es. storie/DaniTeo')
    a.add_argument('--solo', help='solo queste scene, id separati da virgola')
    a.add_argument('--video', action='store_true',
                   help='prompt per animare le immagini (prompt_video.txt, campo "movimento:")')
    a.add_argument('--tpu', action='store_true',
                   help='cartella kaggle_tpu/ per il notebook wan_tpu_kaggle.ipynb')
    a.add_argument('--output', type=Path, default=CARTELLA / 'output',
                   help='dove genera.py ha salvato le immagini (per --video e --tpu)')
    args = a.parse_args()

    cartella = args.cartella
    for nome in ('personaggi.txt', 'stile.txt', 'scene.txt'):
        if not (cartella / nome).is_file():
            sys.exit(f'Manca {cartella / nome}')
    personaggi = leggi_personaggi(cartella / 'personaggi.txt')
    stile = ' '.join(righe_utili(cartella / 'stile.txt'))
    scene = leggi_scene(cartella / 'scene.txt')
    solo = {s.strip() for s in args.solo.split(',')} if args.solo else None

    if args.tpu:
        scrivi_tpu(cartella, scene, stile, solo, args.output)
        return
    if args.video:
        scrivi_video(cartella, scene, stile, solo, args.output)
        return

    righe = []
    for scena in scene:
        if solo and scena['id'] not in solo:
            continue
        if not scena.get('immagine'):
            print(f'  {scena["id"]}: manca "immagine:", salto')
            continue
        riga = (f'{cartella.name}/{scena["id"]} | {componi_prompt(scena, personaggi, stile)} | '
                f'{scena.get("formato", FORMATO)}')
        if scena.get('seed', '').isdigit():
            riga += f' | seed={scena["seed"]}'
        righe.append(riga)

    uscita = cartella / 'prompt_storia.txt'
    intestazione = ['# Generato da prepara_storia.py: non modificatelo a mano, '
                    'cambiate scene.txt e rilanciate lo script.']
    uscita.write_text('\n'.join(intestazione + righe) + '\n', encoding='utf-8')
    print(f'Scritte {len(righe)} scene in {uscita}')


if __name__ == '__main__':
    main()
