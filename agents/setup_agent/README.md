# Setup agent

This agent sets up the IEMP controlled lab environment from start to finish. It
uses the OpenAI Python SDK and Responses API with `gpt-5.3-codex`. Authentication
comes from `OPENAI_API_KEY`. The model receives only three bounded tools: inspect
the host, run the repository installer, and verify the result. It does not
receive arbitrary shell access.

The repository installer remains the source of truth. It installs supported host
prerequisites when necessary, provisions ignored local credentials, builds and
starts the Compose stack, applies migrations, seeds the demo registry, and checks
health. The agent additionally verifies all four services, Alembic head, both
readiness routes, and `device-demo-001` before it can report success.

## Prerequisites

- A supported 64-bit Linux host.
- Python 3.10 or newer with the `venv` module.
- An OpenAI Platform project API key with access to the Responses API and the
  selected model.

Export the API key in the shell that starts the agent. Do not put it in the
repository, command arguments, logs, or screenshots:

```sh
export OPENAI_API_KEY="your-project-api-key"
```

Test authentication, model access, and function calling without changing the
host or platform:

```sh
./agents/setup_agent/run.sh --test-api
```

## Run

From the repository root:

```sh
./agents/setup_agent/run.sh
```

The launcher creates an ignored virtual environment and installs the OpenAI SDK
on first use. Run it as the normal host user. The existing installer invokes
`sudo` only when host packages or Docker access require it. Full installer output
is streamed to the terminal and saved under the ignored
`agents/setup_agent/logs/` directory. Generated credentials are never printed.

If Docker, Compose, Python, and Git are already installed, prevent host package
changes with:

```sh
./agents/setup_agent/run.sh --skip-host-install
```

`gpt-5.3-codex` is the default. Override it only when intentionally testing
another model:

```sh
export SETUP_AGENT_MODEL=gpt-5.3-codex
./agents/setup_agent/run.sh
```

Other controls are available through `./agents/setup_agent/run.sh --help`.

## Test

The unit tests use fakes and neither contact a model nor change the host:

```sh
python3 -m unittest discover -s agents/setup_agent/tests -v
```
