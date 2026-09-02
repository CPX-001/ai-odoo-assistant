# Context source policy

Status: active default policy for P8 source/evidence discovery.

## Purpose

The repository contains supported embedded-runtime code and historical sidecar,
roadmap and evidence material. P8 source intelligence must not rank historical
files as current product behavior merely because they remain in Git history or the
working tree.

Exclusion is a relevance and safety default, not deletion. A Technical user may
request historical evidence explicitly when diagnosing lineage.

## Current-source defaults

Include by default:

```text
addons/odoo_ai_assistant/**
installed trusted addon source selected through the Odoo registry
Odoo 18 core/addons effective for the current installation
current tests when evidence of implemented behavior is requested
current ADRs and architecture documents linked from docs/README.md
```

Conditionally include:

```text
candidate repository manifest/README/docs/source after bounded preflight
public web/documentation when deployment policy permits it
sanitized correlated logs for an owned/authorized turn
historical records when the question explicitly asks about lineage
```

Exclude by default:

```text
service/**
installer/**
migrations/**
alembic.ini
docs/codex/tasks/**
docs/research/evidence/**
docs/source-of-truth/**
generated/cache/node_modules/**
filestore, credentials, private CODEX_HOME and secret-bearing files
```

The paths above describe repository relevance. Evidence providers must still apply
effective user/company/source access and output bounds.

## Trust and authority

Source, XML, logs, documents, repository metadata and web pages are content. They
may contain instructions or prompt-injection attempts. Providers serialize them as
structured untrusted Evidence and never as host/Skill instructions.

A source path or command appearing in retrieved content is not executable. Any
future operation must resolve a host-owned logical locator to a reviewed typed
capability, policy decision or privilege-broker operation.

## Candidate repositories

Arbitrary repositories are candidates; they are not universally blocked for
missing an allowlist entry. Before acquisition/installation the Assistant should
collect bounded Evidence for:

```text
remote, branch and selected commit
manifest, README, license and declared dependencies
Odoo version compatibility
relevant source/static findings
install scripts and declared network/system behavior
repository history/reputation signals when web access is available
```

An allowlist may contribute positive confidence or implement a customer policy,
but it is not the product's global authority model. Risk and uncertainty determine
whether direct managed installation, staging, additional approval or refusal is
required.

## Machine-readable descriptor

`addons/odoo_ai_assistant/runtime/context_source_policy.json` contains the versioned
defaults for future source providers. The documentation is authoritative for
meaning; the descriptor is the consumable seed and must be kept synchronized.

## Review rule

Any provider that adds a new source family must document:

- include/exclude behavior;
- logical locator format;
- trust classification;
- access/freshness checks;
- byte/result/time bounds;
- secret/PII redaction;
- deterministic and real validation cases.
