### `AGENTS.md`


# AGENTS – fejlesztői környezet és kódolási konvenciók (Codex-nek)

## 0) Repo elrendezés

```
.
├─ libs/
│  └─ accscore/           # Git submodule: [https://github.com/kolosmile/accs-core](https://github.com/kolosmile/accs-core)
├─ src/
│  └─ accs\_app/           # Ennek az alkalmazásnak a forrása
├─ tests/
├─ pyproject.toml
└─ AGENTS.md
```


> **Kritikus:** az `accscore` **submodule-ként** van jelen a `libs/accscore` útvonalon, és **telepíteni kell** (`pip install -e libs/accscore`), különben az importok és a tesztek nem fognak futni.

---

## 1) Fejlesztői környezet – Setup (venv + függőségek)

**Lépések (Codex futtassa ezeket a klónozás után):**
```bash
# Submodule inicializálás
git submodule update --init --recursive

# Virtuális környezet
python -m venv .venv
. .venv/bin/activate
pip install -U pip

# ACCScore telepítése (submodule-ból, szerződés szerint)
pip install -e libs/accscore

# Saját alkalmazás telepítése (editable)
pip install -e .

# Fejlesztői eszközök (lint, típus, teszt)
pip install ruff mypy pytest
````

**Megjegyzések Codex-nek:**

* **Python 3.11+** szükséges (PEP 585 generikusok, Pydantic v2).
* A tesztek futtatása: `pytest -q`.
* Lint: `ruff .` ; Típus: `mypy .`

---

## 2) Submodule kezelés (pinelés és frissítés)

* Első felvétel (emberi lépés, info Codex-nek is hasznos):

  ```bash
  git submodule add https://github.com/kolosmile/accs-core libs/accscore
  git -C libs/accscore checkout <PINELT-COMMIT-OR-BRANCH>
  git commit -m "Add accscore submodule"
  ```
* Frissítés később:

  ```bash
  git submodule update --remote --merge libs/accscore
  # ha kell: git -C libs/accscore checkout <uj-pin>
  ```

---

## 3) Kódolási konvenciók

### 3.1 Docstring (Google style, PEP257)

* Kötelező: publikus **függvény**, **osztály**, **modul**.
* Írd le: **miért** (intent), **Args**, **Returns**, **Raises**, invariánsok/mellékhatások.

**Minta**

```python
def claim_tasks(service: str, limit: int) -> list[JobTask]:
    """Select and claim runnable tasks for a service.

    Args:
        service: Logical service name (e.g., "renderer").
        limit: Positive upper bound for claimed tasks.

    Returns:
        Tasks ordered by global job sequence; length <= limit.

    Raises:
        ValueError: If limit <= 0.
    """
```

### 3.2 Pydantic (V2) szabályok

* **Szerializáció:** `model_dump()` / `model_dump_json()`.
* **Kollekciós defaultok:** `Field(default_factory=list|dict|set)`.
* **Enumok:** minden lezárt értékkészletre (státuszok, típusok).
* **Validátorok:** invariáns/formaellenőrzés; üzleti logikát ne itt tartsunk.
* **Határvédelem:** DB/API/raw → **először** Pydantic modell, utána dolgozz vele tovább.

### 3.3 Kommentelés (a *miért*-re fókuszálj)

* Címkék: `TODO(owner): … [#issue]`, `FIXME: …`, `HACK: …`, `NOTE: …`
* Példa:

  ```python
  # NOTE: FOR UPDATE SKIP LOCKED to avoid contention; global order by jobs.order_seq.
  # TODO(kristof): Replace ad-hoc backoff with exponential policy (#142)
  ```

### 3.4 Lint/format és típus

* **Ruff**: lint + format (Google docstring szabályok engedélyezve).
* **Mypy**: szigorúbb alapbeállítás; publikus API típusozott.
* Importok: stdlib → third-party → local; **nincs** wildcard import.
* SQL: **bind paraméter** (nincs f-string), zárolási/izolációs döntés **kommentelve**.

---

## 4) Tesztelés – minimális elvárások

* Minden új modulhoz legalább 1–2 **smoke** teszt.
* Pydantic kollekciós mezők: **default izoláció** (külön példányok).
* Agent/builder loopok: **Given/When/Then** jellegű rövid tesztek.

---

## 5) CI (iránymutatás)

* Követelmény a zöld: `ruff`, `mypy`, `pytest`.
* (A CI pipeline-t a projekt később tölti fel; Codex lokálisan futtassa a fenti parancsokat.)
