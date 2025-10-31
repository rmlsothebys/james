
# BaT → JamesEdition Feed (Auto)

Acest proiect creează un feed XML pentru **JamesEdition** pe baza loturilor **unsold** de pe Bring a Trailer (BaT) și îl publică automat.
Implicit, publicarea se face către **GitHub Pages** (gratuit). Opțional, poți activa publicarea într-un bucket **S3/R2**.

> ⚠️ **Legal/TOS**: Folosește scriptul doar pentru mașinile pe care le reprezinți. Evită copierea integrală a textelor/pozelor BaT; în feed recomandăm să pui descrieri și imagini proprii. Respectă Terms of Service și robots ale BaT.

---

## Ce face

1. Preia periodic `https://bringatrailer.com/auctions/results/?result=unsold` (+ paginare).
2. Deschide fiecare listing și extrage: titlu, an, marcă, model, VIN (dacă apare), kilometraj/mile, transmisie, imagini, descriere scurtă.
3. Generează un **XML JamesEdition** (`version="3.0"`) cu nume **static**:
   - `JamesEdition_feed_{DEALER_ID}.xml`
4. Publică fișierul:
   - **implicit** pe **GitHub Pages** → URL stabil de feed
   - **opțional** pe **S3/R2** (dacă pui credențiale)

---

## Setup rapid (varianta GitHub Pages – recomandat)

1. **Creează un repo GitHub** nou, numit oricum. (De ex. `bat-je-feed`)
2. Descarcă arhiva din această pagină și pune conținutul în repo.
3. În GitHub → **Settings → Pages**: setează **Source = GitHub Actions**.
4. În GitHub → **Settings → Secrets and variables → Actions → New repository secret**, adaugă:
   - `JE_DEALER_ID` – ID-ul tău JamesEdition (număr).
   - `JE_DEALER_NAME` – numele business-ului tău (cum apare în JE).
   - (opțional) `FEED_TITLE` / `FEED_REFERENCE` pentru branding feed.
5. În **Actions**, workflow-ul `Publish JamesEdition Feed` se va rula la ore fixe (cron) și la push.
6. După ce rulează, vei avea pagina **GitHub Pages** activă (în tab-ul **Deployments → GitHub Pages**).
   - URL-ul fișierului va fi de forma:
     `https://<user>.github.io/<repo>/JamesEdition_feed_<JE_DEALER_ID>.xml`
7. Intră în contul tău **JamesEdition** → **Listings → Add via Feed (XML)** și introdu URL-ul de mai sus.

> JamesEdition citește feed-ul de câteva ori pe zi. Ține URL-ul și numele fișierului **fixe**.

---

## Setup opțional S3 / Cloudflare R2

Adaugă încă **secrete** în GitHub:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION` (ex. `us-east-1`)
- `S3_BUCKET` (ex. `my-je-feed`)
- `S3_PREFIX` (ex. `feeds/` – opțional)
- `S3_ENDPOINT_URL` (opțional pentru R2, ex. `https://<accountid>.r2.cloudflarestorage.com`)

Activează în workflow secțiunea **Upload to S3** (este deja inclusă, se execută doar dacă detectează `S3_BUCKET`).

---

## Rulare locală (pentru test)

```bash
python -m venv .venv && source .venv/bin/activate  # pe Windows: .venv\Scripts\activate
pip install -r requirements.txt
export JE_DEALER_ID=123456
export JE_DEALER_NAME="Dealer SRL"
python app/main.py
ls -l JamesEdition_feed_$JE_DEALER_ID.xml
```

---

## Note tehnice

- Respectă robots: scriptul introduce un `User-Agent` și rate limiting.
- Selectorii BaT pot varia. Am adăugat fallback-uri și detecții robuste.
- Dacă nu există preț, setăm `<price_on_request>yes</price_on_request>` și lăsăm `<price/>` gol.
- Imaginile din feed ar trebui să fie **ale tale** sau cu drept de utilizare; poți configura ca scriptul să folosească un set de imagini proprii per model (vezi `IMAGE_HOST_BASE` în `config.py`).

---

## Customizări utile

În `config.py`:
- `MAX_LISTINGS` (default 120)
- `PAUSE_BETWEEN_REQUESTS` (default 0.9s)
- `IMAGE_HOST_BASE` (dacă vrei să înlocuiești imaginile din BaT cu cele proprii)
- `FEED_VERSION`, `FEED_REFERENCE`, `FEED_TITLE`

---

## Suport

Dacă întâmpini erori la workflow (Actions), verifică tab-ul **Actions** → run logs. De obicei lipsesc variabilele de mediu sau repo-ul nu are încă activat Pages.
