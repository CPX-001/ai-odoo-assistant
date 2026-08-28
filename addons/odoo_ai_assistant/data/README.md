# Odoo data records

This directory contains XML data installed/updated with the addon. These records support runtime lifecycle rather than defining agent intelligence.

## Current files

### `turn_cron.xml`

Defines the native Odoo cron work used to claim/process durable Assistant turns. The embedded architecture relies on Odoo scheduling instead of a permanent Assistant daemon or external queue.

At the current state there are two cron runner slots; configurable/measured concurrency and backpressure are later Phase 5 work.

### `retired_sidecar_cleanup.xml`

Carries cleanup/retirement data for the old sidecar architecture. It exists so upgrades do not accidentally leave obsolete scheduled/configuration behavior active.

It is historical migration support, not evidence that the sidecar is still part of the product.

## Rule for new data records

Add XML here when a record is part of addon installation/lifecycle and has a stable technical identity.

Do not use XML data to create a hidden second capability registry. Executable capabilities belong in the capability framework; admin configuration belongs in Odoo models/views.
