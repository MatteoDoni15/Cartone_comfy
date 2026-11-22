"""Crea la voce di ogni scena con Kokoro (sintesi vocale open, gira sul PC, offline).

Per ogni scena di <cartella>/scene.txt:
  - se ci sono righe "parla: Nome | battuta", legge le battute con la voce del personaggio;
  - altrimenti legge la "narrazione:" con la voce narrante.
Scrive <cartella>/voce/<id>.wav, che monta_video.py mette nel video.

Uso:
    python voce.py storie/DaniTeo
    python voce.py storie/DaniTeo --rifai            rifà anche quelle già fatte
    python voce.py storie/DaniTeo --solo 03_prima_tu

La prima volta:
    pip install kokoro-onnx soundfile
    e i due file del modello in modelli/kokoro/ (vedi README).
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from prepara_storia import leggi_scene

CARTELLA = Path(__file__).resolve().parent
MODELLO = CARTELLA / 'modelli' / 'kokoro' / 'kokoro-v1.0.onnx'
VOCI_FILE = CARTELLA / 'modelli' / 'kokoro' / 'voices-v1.0.bin'

# Personaggio -> (voce Kokoro, velocità). Voci italiane: if_sara (donna), im_nicola (uomo).
VOCI = {
    'Narratore': ('im_nicola', 0.9),
    'Teo': ('im_nicola', 1.0),
    'Dani': ('if_sara', 1.0),
}
PAUSA = 0.45  # secondi di silenzio tra una battuta e l'altra


def pulisci(testo):
    """Toglie virgolette e caporali, che la voce leggerebbe male."""
    return re.sub(r'\s+', ' ', re.sub(r'[«»"“”]', '', testo)).strip()


def main():
    a = argparse.ArgumentParser(description='Crea la voce delle scene con Kokoro.')
    a.add_argument('cartella', type=Path, help='cartella della storia, es. storie/DaniTeo')
    a.add_argument('--solo', help='solo queste scene, id separati da virgola')
    a.add_argument('--rifai', action='store_true', help='rifà anche le voci già create')
    args = a.parse_args()

    if not MODELLO.is_file() or not VOCI_FILE.is_file():
        sys.exit(f'Mancano i file del modello in {MODELLO.parent} (vedi README).')
    from kokoro_onnx import Kokoro
    kokoro = Kokoro(str(MODELLO), str(VOCI_FILE))

    uscita = args.cartella / 'voce'
    uscita.mkdir(exist_ok=True)
    solo = {s.strip() for s in args.solo.split(',')} if args.solo else None

    for scena in leggi_scene(args.cartella / 'scene.txt'):
        if solo and scena['id'] not in solo:
            continue
        file = uscita / f'{scena["id"]}.wav'
        if file.exists() and not args.rifai:
            print(f'  {scena["id"]:<24} già fatta')
            continue
        battute = scena['parla'] or (
            [('Narratore', scena['narrazione'])] if scena.get('narrazione') else [])
        if not battute:
            print(f'  {scena["id"]:<24} niente da leggere')
            continue

        pezzi, frequenza = [], 24000
        for chi, testo in battute:
            if chi not in VOCI:
                sys.exit(f'Scena {scena["id"]}: nessuna voce per "{chi}" (aggiungetela a VOCI in voce.py)')
            voce, velocita = VOCI[chi]
            audio, frequenza = kokoro.create(pulisci(testo), voice=voce, speed=velocita, lang='it')
            if pezzi:
                pezzi.append(np.zeros(int(PAUSA * frequenza), dtype=audio.dtype))
            pezzi.append(audio)
        audio = np.concatenate(pezzi)
        sf.write(file, audio, frequenza)
        print(f'  {scena["id"]:<24} {len(audio) / frequenza:4.1f} s  ({", ".join(c for c, _ in battute)})')


if __name__ == '__main__':
    main()
