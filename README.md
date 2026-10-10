# YouTube-linkkien kerääjä

Graafinen sovellus (selainversio ja PySide6-työpöytäversio), joka kerää YouTube-kanavan videoiden linkit
[yt-dlp](https://github.com/yt-dlp/yt-dlp):n avulla. Videotiedostoja **ei** ladata – vain
luettelotiedot.

## Ominaisuudet

- Kanavaosoite eri muodoissa: `/@kanava`, `/channel/UC…`, `/c/nimi`, `/user/nimi`, myös pelkkä
  `@kanava` tai `UC…`-tunnus sekä välilehdelliset osoitteet (`…/videos`, `…/shorts`).
- Valinta: kaikki videot / Shorts / livelähetykset (voi valita useita). Duplikaatit poistetaan video-ID:n perusteella.
- Näkymä: vain linkit tai linkit + otsikot + julkaisupäivät (+ kesto, tyyppi, kanava).
- Haku ajetaan erillisessä säikeessä: käyttöliittymä ei jäädy, löydetyt videot ilmestyvät
  taulukkoon sitä mukaa, haun voi peruuttaa.
- Suodatus otsikon perusteella (kaikkien hakusanojen on löydyttävä, kirjainkoko ei vaikuta) ja tyypin mukaan.
- Kopioi kaikki linkit, Vie TXT, Vie CSV (tallennuspaikan valitset itse), Avaa linkki valitulle videolle
  (myös rivin tuplaklikkaus).
- Virheet (virheellinen osoite, verkkovirhe, YouTuben pyyntörajoitus, botintunnistus) näytetään
  selkeästi ja **Yritä uudelleen** -painikkeella haun voi toistaa.
- Kapea ikkuna / puhelin: asettelu pinoutuu, taulukon rivit muuttuvat korteiksi.

### Tärkeää tuloksista

- **Osittaiset tulokset ilmoitetaan.** Jos haku keskeytyy virheeseen, peruutetaan tai rajataan
  ”Enintään”-valinnalla, sovellus näyttää varoituksen eikä väitä kaikkien videoiden löytyneen.
- Kopiointi ja vienti koskevat **näkyvillä olevia rivejä**: ilman suodatinta kaikkia, suodattimella vain osumia.
- Kanavalistaus ei yleensä sisällä julkaisupäivää. Päivä-sarake on silloin ”–”, ellei valita
  **Hae tarkat julkaisupäivät (hidas)**, joka tekee yhden pyynnön per video (4 rinnakkain) ja voi
  kestää pitkään suurilla kanavilla sekä lisätä pyyntörajoituksen riskiä.
- CSV tallennetaan UTF-8-BOM-koodauksella, jotta Excel näyttää ääkköset oikein. TXT on UTF-8 ilman BOM:ia.
  - TXT, vain linkit: yksi URL per rivi. TXT, laaja näkymä: `otsikko<TAB>URL<TAB>päivä`.
  - CSV-sarakkeet: `title,url,video_id,upload_date,duration_seconds,channel,type` (vain linkit: `url`).

## Käynnistys – selainversio (suositeltu)

Vaatii Python 3.9+ (testattu 3.13). Selainversio ajaa haun omalla koneellasi pienellä paikallisella
palvelimella (selain ei voi hakea YouTubea suoraan, eikä yt-dlp toimi selaimessa) ja avaa käyttöliittymän selaimeen.

**Windows:** tuplaklikkaa `start.bat`  ·  **Linux / macOS:** `./start.sh`

Skripti luo `.venv`-ympäristön, asentaa riippuvuudet (`requirements.txt`: yt-dlp, Flask) ja avaa
http://127.0.0.1:8765/ selaimessa. Käsin: `pip install -r requirements.txt && python -m ytlinks.web`.
Lopetus: Ctrl+C. Valinnat: `--port 9000`, `--no-browser`, `--host …`.

**Käyttö puhelimella:** käynnistä palvelin tietokoneella komennolla `./start.sh --host 0.0.0.0`
(Windows: `start.bat --host 0.0.0.0`) ja avaa puhelimen selaimessa `http://<koneen-IP>:8765/`
samassa Wi-Fi-verkossa. Haku tehdään silti tietokoneella, ei puhelimessa. Sovelluksessa ei ole
kirjautumista, joten älä avaa sitä julkiseen verkkoon; palomuuri voi pyytää sallimaan yhteyden.
Tiedostot (TXT/CSV) latautuvat selaimen latauskansioon.

## Käynnistys – työpöytäversio (PySide6)

**Windows:** `start_desktop.bat`  ·  **Linux / macOS:** `./start_desktop.sh`
(käsin: `pip install -r requirements-desktop.txt && python -m ytlinks`)

- Linux: PySide6 tarvitsee järjestelmäkirjastoja, esim. Debian/Ubuntu: `sudo apt install libegl1 libxkbcommon0 libfontconfig1 libdbus-1-3`.
- macOS: sama skripti; ei testattu macOS:llä.
- YouTube muuttuu usein; jos haku alkaa epäonnistua, päivitä yt-dlp: `pip install -U yt-dlp`.

## Testit

```
pip install -r requirements-dev.txt   # sisältää työpöytäriippuvuudet ja PyInstallerin
python -m pytest
```

Testit kattavat URL-tunnistuksen, duplikaattien poiston, suodatuksen, TXT/CSV-viennin (ääkköset),
haun logiikan vale-yt-dlp:llä (osittaiset virheet, peruutus, puuttuva välilehti, rajaus, tarkat päivät)
web-rajapinnan (Flask test client) ja työpöytä-GUI:n savutestit `offscreen`-tilassa. **Testit eivät tee oikeita YouTube-hakuja.**

## Rakenne

```
ytlinks/
  models.py      tietomallit (Video, FetchOptions, FetchResult)
  urls.py        kanavaosoitteiden tunnistus ja normalisointi
  fetcher.py     yt-dlp-haut (välilehdittäin, laiska sivutus, peruutus, tarkat päivät)
  results.py     duplikaattien poisto, suodatus, muotoilu
  exporters.py   TXT- ja CSV-vienti
  errors.py      virheluokat ja virheiden muuttaminen käyttäjäviesteiksi
  gui/           PySide6-työpöytäkäyttöliittymä: pääikkuna, taulukkomalli, työsäie
  web/           selainversio: Flask-palvelin (server.py), taustahaut (jobs.py), static/ (HTML/CSS/JS)
tests/
```

## Itsenäinen ohjelma (ei Python-komentoa)

Tämä koskee työpöytäversiota. PyInstaller paketoi sovelluksen ja Pythonin yhteen kansioon. Ajettava siinä käyttöjärjestelmässä,
jolle ohjelma halutaan (Windows-versio rakennetaan Windowsissa jne.):

- Windows: `build_exe.bat` → `dist\YouTubeLinkkienKeraaja\YouTubeLinkkienKeraaja.exe`
- Linux / macOS: `./build_exe.sh` → `dist/YouTubeLinkkienKeraaja/`

Kansio on noin 170 MB. Yhden tiedoston versio: lisää PyInstaller-komentoon `--onefile` (käynnistyy hitaammin).
Linux-versio on rakennettu ja käynnistetty kehitysympäristössä; Windows- ja macOS-rakennusta ei ole testattu.

## Rajoitukset

- Selainversion haku ajetaan aina palvelimella (yleensä omalla tietokoneellasi), ei puhelimessa. Pelkkä
  staattinen sivu ilman palvelinta ei voi toimia, koska selain ei saa hakea YouTubea suoraan.
- Selainversion palvelin on tarkoitettu henkilökohtaiseen käyttöön (ei kirjautumista, Flaskin kehityspalvelin).
  Haut ovat muistissa: palvelimen uudelleenkäynnistys tyhjentää ne.
- Selainversion CSV:ssä otsikot/kanavat, jotka alkavat merkillä `= + - @`, saavat eteensä `'`, jotta Excel ei tulkitse niitä kaavoiksi.
- YouTube voi rajoittaa pyyntöjä (HTTP 429), vaatia botintunnistusta tai muuttaa sivurakennettaan,
  jolloin haku jää osittaiseksi tai epäonnistuu. Sovellus ilmoittaa tämän.
- Vain julkiset kanavasivut; kirjautumista tai evästeitä ei tueta. Ikärajoitetut/yksityiset videot
  eivät välttämättä näy.
- Livelähetykset-välilehti sisältää myös päättyneet ja tulevat lähetykset sen mukaan kuin YouTube ne listaa.
