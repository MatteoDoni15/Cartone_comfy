"""Monta una storia in un video con ffmpeg: clip animate (o immagini con zoom), voce, musica.

Per ogni scena di <cartella>/scene.txt, nell'ordine:
  - VIDEO: l'ultima clip in output/<Storia>_video/<id>_*.webm|mp4 (fatta con Wan);
    se non c'è, l'immagine (scelte/<id>.png, altrimenti l'ultima in output/<Storia>/)
    con uno zoom lento;
  - VOCE:  <cartella>/voce/<id>.wav, se c'è (fatta con voce.py);
  - durata: quanto serve alla voce (o alla narrazione), mai meno di 4 secondi.
    Se la clip è più corta resta ferma sull'ultimo fotogramma, se è più lunga si taglia.

Scrive <cartella>/<Storia>.mp4 e accanto <Storia>.srt con la narrazione.

Uso:
    python monta_video.py storie/DaniTeo
    python monta_video.py storie/DaniTeo --musica canzone.mp3
    python monta_video.py storie/DaniTeo --sottotitoli-nel-video   (per WhatsApp & co.)
    python monta_video.py storie/DaniTeo --senza-clip               (solo immagini con zoom)

Serve ffmpeg (su Windows: scoop install ffmpeg  oppure  winget install Gyan.FFmpeg).
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from prepara_storia import leggi_scene, trova_immagine

CARTELLA = Path(__file__).resolve().parent
FPS = 25
LARGHEZZA, ALTEZZA = 1920, 1080
DISSOLVENZA = 1.0     # secondi di passaggio tra una scena e l'altra
ZOOM = 0.06           # quanto avvicina/allontana un'immagine ferma (0.06 = 6%)
ATTACCO_VOCE = 0.6    # la voce parte poco dopo l'inizio della scena
CODA_VOCE = 0.9       # silenzio dopo la voce prima di passare alla scena dopo
FINALE_EXTRA = 3.0    # secondi in più sull'ultima scena
VOLUME_MUSICA = 0.25  # musica sotto la voce (1 = volume originale)


def trova_clip(output, storia, scena):
    clip = [f for f in (output / f'{storia}_video').glob(f'{scena}_*.*')
            if f.suffix.lower() in ('.webm', '.mp4')]
    return max(clip, key=lambda f: f.stat().st_mtime) if clip else None


def durata_audio(file):
    import soundfile
    return soundfile.info(str(file)).duration


def tempo_srt(secondi):
    ms = round(secondi * 1000)
    return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}'


def main():
    a = argparse.ArgumentParser(description='Monta una storia in un video.')
    a.add_argument('cartella', type=Path, help='cartella della storia, es. storie/DaniTeo')
    a.add_argument('--output', type=Path, default=CARTELLA / 'output',
                   help='dove genera.py ha salvato immagini e clip (default: output)')
    a.add_argument('--musica', type=Path, help='file audio di sottofondo (sfuma alla fine)')
    a.add_argument('--senza-clip', action='store_true', help='usa solo le immagini, con lo zoom')
    a.add_argument('--senza-voce', action='store_true', help='non mette la voce')
    a.add_argument('--sottotitoli-nel-video', action='store_true',
                   help='scrive la narrazione dentro il video invece che solo nel file .srt')
    a.add_argument('--ffmpeg', default=shutil.which('ffmpeg') or 'ffmpeg')
    args = a.parse_args()

    cartella = args.cartella.resolve()
    output = args.output.resolve()
    if not shutil.which(args.ffmpeg) and not Path(args.ffmpeg).is_file():
        sys.exit('ffmpeg non trovato. Installatelo (scoop install ffmpeg) o usate --ffmpeg percorso.')
    if args.musica and not args.musica.is_file():
        sys.exit(f'File musica non trovato: {args.musica}')

    # --- Cosa c'è per ogni scena ---
    scene = []
    elenco = leggi_scene(cartella / 'scene.txt')
    for n, s in enumerate(elenco):
        clip = None if args.senza_clip else trova_clip(output, cartella.name, s['id'])
        immagine = trova_immagine(cartella, output, s['id'])
        voce = cartella / 'voce' / f'{s["id"]}.wav'
        voce = voce if voce.is_file() and not args.senza_voce else None
        if not clip and not immagine:
            print(f'  {s["id"]:<24} MANCA, salto la scena')
            continue
        if voce:
            durata = ATTACCO_VOCE + durata_audio(voce) + CODA_VOCE + DISSOLVENZA / 2
        else:
            durata = 2.0 + len(s.get('narrazione', '').split()) / 2.5
        durata = max(4.0, durata) + (FINALE_EXTRA if n == len(elenco) - 1 else 0.0)
        scene.append({'scena': s, 'clip': clip, 'immagine': immagine, 'voce': voce,
                      'durata': durata})
        print(f'  {s["id"]:<24} {"clip" if clip else "immagine":<9} '
              f'{"voce" if voce else "    "} {durata:4.1f} s')
    if not scene:
        sys.exit('Nessuna immagine trovata: generate prima le scene con genera.py.')

    totale = sum(x['durata'] for x in scene) - DISSOLVENZA * (len(scene) - 1)
    inizi, t = [], 0.0
    for x in scene:
        inizi.append(t)
        t += x['durata'] - DISSOLVENZA

    # --- Ingressi di ffmpeg ---
    comando = [args.ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-stats']
    ingressi = 0

    def ingresso(file, opzioni=()):
        nonlocal ingressi
        comando.extend([*opzioni, '-i', str(file)])
        ingressi += 1
        return ingressi - 1

    filtri = []
    grande = f'{LARGHEZZA * 2}:{ALTEZZA * 2}'  # lo zoom lavora in grande: non trema
    for i, x in enumerate(scene):
        d = x['durata']
        if x['clip']:
            k = ingresso(x['clip'])
            filtri.append(
                f'[{k}:v]scale={LARGHEZZA}:{ALTEZZA}:force_original_aspect_ratio=increase,'
                f'crop={LARGHEZZA}:{ALTEZZA},setsar=1,fps={FPS},'
                f'tpad=stop_mode=clone:stop_duration={d:.3f},trim=duration={d:.3f},'
                f'setpts=PTS-STARTPTS,format=yuv420p[v{i}]')
        else:
            k = ingresso(x['immagine'])
            fotogrammi = round(d * FPS)
            z = (f'1+{ZOOM}*on/{fotogrammi}' if i % 2 == 0 else f'1+{ZOOM}-{ZOOM}*on/{fotogrammi}')
            filtri.append(
                f'[{k}:v]scale={grande}:force_original_aspect_ratio=decrease,'
                f'pad={grande}:(ow-iw)/2:(oh-ih)/2:color=0xF7F2EA,setsar=1,'
                f"zoompan=z='{z}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={fotogrammi}:"
                f's={LARGHEZZA}x{ALTEZZA}:fps={FPS},format=yuv420p[v{i}]')
    ultimo = 'v0'
    for i in range(1, len(scene)):
        filtri.append(f'[{ultimo}][v{i}]xfade=transition=fade:duration={DISSOLVENZA}:'
                      f'offset={inizi[i]:.3f}[x{i}]')
        ultimo = f'x{i}'

    # --- Sottotitoli: durante la voce, o mentre la scena è a schermo ---
    srt = cartella / f'{cartella.name}.srt'
    voci_srt = []
    for i, x in enumerate(scene):
        testo = x['scena'].get('narrazione')
        if not testo:
            continue
        if x['voce']:
            da = inizi[i] + ATTACCO_VOCE
            a_ = da + durata_audio(x['voce']) + 0.4
        else:
            da = inizi[i] + (DISSOLVENZA / 2 if i else 0.3)
            a_ = inizi[i] + x['durata'] - DISSOLVENZA / 2
        voci_srt.append(f'{len(voci_srt) + 1}\n{tempo_srt(da)} --> {tempo_srt(a_)}\n{testo}\n')
    srt.write_text('\n'.join(voci_srt), encoding='utf-8')

    finale = f'[{ultimo}]fade=t=in:d=1,fade=t=out:st={totale - 1.5:.3f}:d=1.5'
    if args.sottotitoli_nel_video:
        # Percorso relativo (ffmpeg gira dentro la cartella): evita i problemi con "C:".
        finale += (f",subtitles={srt.name}:force_style='FontName=Georgia,FontSize=20,"
                   "PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=1,"
                   "Outline=2,Shadow=0,MarginV=40'")
    filtri.append(finale + '[video]')

    # --- Audio: voci al loro posto + musica sotto ---
    tracce = []
    for i, x in enumerate(scene):
        if x['voce']:
            k = ingresso(x['voce'])
            ritardo = round((inizi[i] + ATTACCO_VOCE) * 1000)
            filtri.append(f'[{k}:a]aresample=48000,aformat=channel_layouts=stereo,'
                          f'adelay={ritardo}:all=1[a{i}]')
            tracce.append(f'[a{i}]')
    if args.musica:
        # Tagliata (e ripetuta, se è corta) già in ingresso: lunga quanto il video.
        k = ingresso(args.musica, ['-stream_loop', '-1', '-t', f'{totale:.3f}'])
        volume = VOLUME_MUSICA if tracce else 1.0
        filtri.append(f'[{k}:a]aresample=48000,aformat=channel_layouts=stereo,'
                      f'volume={volume},'
                      f'afade=t=out:st={max(0, totale - 3):.3f}:d=3[musica]')
        tracce.insert(0, '[musica]')
        filtri.append(f'{"".join(tracce)}amix=inputs={len(tracce)}:normalize=0:'
                      f'duration=first[audio]')
    elif tracce:
        filtri.append(f'{"".join(tracce)}amix=inputs={len(tracce)}:normalize=0:'
                      f'duration=longest,apad,atrim=0:{totale:.3f}[audio]')

    video = cartella / f'{cartella.name}.mp4'
    comando += ['-filter_complex', ';'.join(filtri), '-map', '[video]']
    if tracce:
        comando += ['-map', '[audio]', '-c:a', 'aac', '-b:a', '192k']
    # yuv420p: l'unico formato che aprono tutti i lettori (Windows, telefoni, WhatsApp).
    comando += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-profile:v', 'high',
                '-preset', 'medium', '-crf', '18', '-r', str(FPS),
                '-t', f'{totale:.3f}', '-movflags', '+faststart', video.name]

    print(f'\nMonto {len(scene)} scene, {totale:.0f} secondi...')
    risultato = subprocess.run(comando, cwd=cartella)
    if risultato.returncode != 0:
        sys.exit('ffmpeg ha dato errore (vedi sopra).')
    print(f'\nFatto: {video}\nSottotitoli: {srt}')


if __name__ == '__main__':
    main()
