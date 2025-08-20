IMAGE_BUILDER ?= accs-daemon-builder:local
IMAGE_AGENT  ?= accs-daemon-agent:local

.RECIPEPREFIX = >

.PHONY: build-builder build-agent run-builder run-agent

build-builder:
>docker build -f docker/Dockerfile.builder -t $(IMAGE_BUILDER) .

build-agent:
>docker build -f docker/Dockerfile.agent -t $(IMAGE_AGENT) .

run-builder: build-builder
>docker run --rm -e ACC_DB_URL=sqlite:// $(IMAGE_BUILDER) --once --dsn sqlite://

run-agent: build-agent
>docker run --rm -e ACC_DB_URL=sqlite:// $(IMAGE_AGENT) --once --service echo --node n1 --dsn sqlite://
