# Backrest for Home Assistant

A custom integration that brings the backups made by [Backrest](https://github.com/garethgeorge/backrest), the web UI and scheduler for [restic](https://restic.net), into Home Assistant.

For every Backrest instance you add, you get:

- a device per **backup plan**, with:
  - status of the newest backup (pending, in progress, success, warning, error, cancelled)
  - progress of a running backup (%)
  - time of the last finished backup and of the next scheduled one
  - data added and duration of the last backup
  - last error message
  - protected data (size of the newest good snapshot)
  - successful, warning and failed backups over the last 30 days
  - binary sensors *Backup running* and *Problem* (last backup failed, or the plan is overdue according to Backrest)
- a device per **repository**, with the number of snapshots and the data added over 30 days.

New plans and repositories show up by themselves. Removed ones become unavailable and can then be deleted from the device page.

> Status: early development (v0.1). The integration polls Backrest once a minute. Live progress via Backrest's event stream, buttons to start or cancel a backup and events for automations are planned.

## Requirements

- Home Assistant 2025.10 or newer
- Backrest 1.14 or newer, reachable from Home Assistant over HTTP(S)

Home Assistant talks to Backrest directly, so use an address on your LAN (for example `http://192.168.1.10:9898`). A reverse proxy works too, as long as it does not put a login page in front of Backrest.

## Installation

### HACS (custom repository)

1. In HACS, open the menu in the top right and choose **Custom repositories**.
2. Add `https://github.com/fmeesters/ha-backrest` with type **Integration**.
3. Install **Backrest** and restart Home Assistant.

### Manual

Copy `custom_components/backrest` into the `custom_components` folder of your Home Assistant configuration and restart Home Assistant.

## Configuration

1. In Backrest, create a user for Home Assistant (*Settings → Users*). Backrest only knows full users, so this user can also start backups.
2. In Home Assistant, go to **Settings → Devices & services → Add integration** and pick **Backrest**.
3. Enter the URL, user name and password. Leave the user name empty if authentication is disabled in Backrest.

Repeat for every Backrest instance. Each one is identified by its instance name, so the same instance cannot be added twice. The URL and credentials can be changed later with **Reconfigure**; when Backrest rejects the password, Home Assistant asks for a new one.

## How it works

Backrest exposes its API as [Connect RPC](https://connectrpc.com) (JSON over HTTP POST). The integration calls:

| Method | Used for |
| --- | --- |
| `GetConfig` | instance name, plans and repositories |
| `GetSummaryDashboard` | 30-day statistics, next backup, protected data, overdue flag |
| `GetOperations` (last 40 per plan) | newest and newest finished backup, progress, errors |

The API client lives in `custom_components/backrest/api/` and has no Home Assistant imports.

## Diagnostics

The diagnostics download leaves out the password, user name, URL, repository URIs and backup paths.

## Development

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
ruff format . && ruff check . && mypy custom_components && pytest --cov
```

## License

MIT
