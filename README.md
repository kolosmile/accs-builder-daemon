# accs-daemon

Ez egy monorepo, két külön deployálható komponenssel: builder (`accs_builder_daemon`) és agent (`accs_agent`).

## Gyors példa

```bash
pip install -e libs/accscore
pip install -e .
```

### Builder

```bash
accs-builder --once --dsn sqlite://
```

### Agent

```bash
accs-agent --once --service echo --node n1 --dsn sqlite://
```

## Submodule

A `libs/accscore` könyvtár egy Git submodule és **csak olvasható**.
