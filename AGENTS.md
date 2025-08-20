# AGENTS – fejlesztői környezet és kódolási konvenciók (Codex-nek)

Ez a repó (**accs-daemon**) egy monorepo, két külön deployálható komponenssel: builder (`accs_builder_daemon`) és agent (`accs_agent`).

Példák:
```
accs-builder --once --dsn sqlite://
accs-agent --once --service echo --node n1 --dsn sqlite://
```

> **SUBMODULE POLICY (FONTOS, Codex!)**
>
> - A `libs/accscore` **Git submodule**, **CSAK OLVASÁSRA**.
> - **TILOS** bármit módosítani a `libs/accscore/` alatt ebben a repo-ban.
> - Ha az ACCScore-ban változtatni kell: **PR az accs-core repo-ban**, majd itt **pineld/frissítsd** a submodule-t az új commitra.
>   ~~~bash
>   git submodule update --remote --merge libs/accscore
>   # vagy:
>   git -C libs/accscore fetch
>   git -C libs/accscore checkout <commit-or-branch>
>   git add libs/accscore
>   git commit -m "Update accscore submodule -> <sha>"
>   ~~~

---

## 0) Repo elrendezés

```

.
├─ libs/
│  └─ accscore/           # Git submodule: [https://github.com/kolosmile/accs-core](https://github.com/kolosmile/accs-core)
├─ src/
│  ├─ accs\_builder\_daemon/  # Builder komponens
│  ├─ accs\_agent/            # Service agent komponens
│  └─ accs\_infra/            # Közös infrastruktúra
├─ tests/
├─ pyproject.toml
└─ AGENTS.md

```

> **Kritikus:** az `accscore` **submodule-ként** van jelen a `libs/accscore` útvonalon, és **telepíteni kell** (`pip install -e libs/accscore`), különben az importok és a tesztek nem fognak futni.

---

## 1) Fejlesztői környezet – Setup (venv + függőségek)

**Lépések (Codex futtassa ezeket a klónozás után):**
~~~bash
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
~~~

**Megjegyzések Codex-nek:**
- **Python 3.11+** szükséges (PEP 585 generikusok, Pydantic v2).
- Tesztek: `pytest -q`
- Lint: `ruff .`
- Típusellenőrzés: `mypy .`

---

## 2) Submodule kezelés (READ-ONLY, pinelés és frissítés)

- **Ne** szerkeszd a `libs/accscore` tartalmát ebben a repo-ban.
- Első felvétel (emberi lépés – információ Codex-nek is hasznos):
  ~~~bash
  git submodule add https://github.com/kolosmile/accs-core libs/accscore
  git -C libs/accscore checkout <PINELT-COMMIT-OR-BRANCH>
  git commit -m "Add accscore submodule"
  ~~~
- Frissítés/pinelés később:
  ~~~bash
  git submodule update --remote --merge libs/accscore
  # vagy kézzel:
  git -C libs/accscore fetch
  git -C libs/accscore checkout <uj-pin>
  git add libs/accscore
  git commit -m "Update accscore submodule -> <sha>"
  ~~~

---

## 3) Kódolási konvenciók

### 3.1 Docstring (Google style, PEP257)

- Kötelező: publikus **függvény**, **osztály**, **modul**.
- Írd le: **miért** (intent), **Args**, **Returns**, **Raises**, invariánsok/mellékhatások.

**Minta**
~~~python
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
~~~

### 3.2 Pydantic (V2) szabályok

- **Szerializáció:** `model_dump()` / `model_dump_json()`.
- **Kollekciós defaultok:** `Field(default_factory=list|dict|set)`.
- **Enumok:** minden lezárt értékkészletre (státuszok, típusok).
- **Validátorok:** invariáns/formaellenőrzés; üzleti logikát ne itt tartsunk.
- **Határvédelem:** DB/API/raw → **először** Pydantic modell, utána dolgozz vele tovább.

### 3.3 Kommentelés (a *miért*-re fókuszálj)

- Címkék: `TODO(owner): … [#issue]`, `FIXME: …`, `HACK: …`, `NOTE: …`
- Példa:
  ~~~python
  # NOTE: FOR UPDATE SKIP LOCKED to avoid contention; global order by jobs.order_seq.
  # TODO(kristof): Replace ad-hoc backoff with exponential policy (#142)
  ~~~

### 3.4 Lint/format és típus

- **Ruff**: lint + format (Google docstring szabályok engedélyezve).
- **Mypy**: szigorúbb alapbeállítás; publikus API típusozott.
- Importok: stdlib → third-party → local; **nincs** wildcard import.
- SQL: **bind paraméter** (nincs f-string), zárolási/izolációs döntés **kommentelve**.

---

## 4) Tesztelés – minimális elvárások

- Minden új modulhoz legalább 1–2 **smoke** teszt.
- Pydantic kollekciós mezők: **default izoláció** (külön példányok).
- Agent/builder loopok: **Given/When/Then** jellegű rövid tesztek.

---

## 5) CI (iránymutatás)

- Követelmény a zöld: `ruff`, `mypy`, `pytest`.
- (A CI pipeline-t a projekt később tölti fel; Codex lokálisan futtassa a fenti parancsokat.)

---

### (Opcionális) pre-commit védelem a submodule-ra

Ha szeretnél biztosítékot, hogy véletlenül se stagingelj változást a `libs/accscore` alatt, add hozzá a gyökérbe a `.pre-commit-config.yaml`-t ezzel a hookkal:

~~~yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: forbid-submodule-changes
        name: Forbid changes under libs/accscore (read-only submodule)
        entry: bash -c 'if git diff --cached --name-only | grep -q "^libs/accscore/"; then echo "ERROR: Do not modify the accscore submodule (libs/accscore) — it is read-only."; exit 1; fi'
        language: system
        pass_filenames: false
~~~
