# Backrest for Home Assistant

<img src="custom_components/backrest/brand/icon.png" alt="Backrest" width="96" align="right">

A custom integration that brings the backups made by [Backrest](https://github.com/garethgeorge/backrest), the web UI and scheduler for [restic](https://restic.net), into Home Assistant.

For every Backrest instance you add, you get:

- a device per **backup plan**, with:
  - status of the newest backup (pending, in progress, success, warning, error, cancelled)
  - progress of a running backup (%), when it started and its estimated end (run time so far divided by the fraction done)
  - time of the last finished backup and of the next scheduled one
  - data added and duration of the last backup
  - last error message
  - protected data (size of the newest good snapshot)
  - successful, warning and failed backups over the last 30 days
  - binary sensors *Backup running* and *Problem* (last backup failed, or the plan is overdue according to Backrest)
- a `backrest_backup` event when a backup starts, progresses and ends.
- a device per **repository**, with the number of snapshots and the data added over 30 days.

New plans and repositories show up by themselves. Removed ones become unavailable and can then be deleted from the device page.

> Status: early development. Live progress via Backrest's event stream, and buttons to start or cancel a backup are planned. Automations can follow backups with the `backrest_backup` event (see [Events](#events)).

Translations: English, Dutch, German, French and Spanish.

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

## Data updates

The integration polls each Backrest instance once a minute: one `GetConfig`, one `GetSummaryDashboard` and one `GetOperations` call per plan, all on your LAN. While Backrest cannot be reached, its entities become unavailable; they come back by themselves.

Backrest keeps the next scheduled run as a pending operation that starts in the future. The integration ignores those, so *Status* shows the newest real backup.

## Use cases and examples

- Show the state of all backups on a dashboard, with a progress bar while one runs.
- Get a notification when a backup fails or a plan is overdue.
- Keep a long-term history of how much data each backup adds.

Notify when a plan reports a problem:

```yaml
alias: "Backups - Notify on problem"
triggers:
  - trigger: state
    entity_id:
      - binary_sensor.dockervm_appdata_problem
    to: "on"
    for: "00:05:00"
actions:
  - action: notify.notify
    data:
      title: "Backup problem"
      message: >-
        {{ state_attr(trigger.entity_id, 'friendly_name') }}:
        {{ states(trigger.entity_id | replace('binary_sensor.', 'sensor.')
           | replace('_problem', '_last_error')) }}
```

## Events

Besides entities, the integration fires a `backrest_backup` event when a backup starts, makes progress and ends. Every plan uses the same event, so one automation follows all plans, including plans you add later, without listing entity IDs.

| Field | Meaning |
| --- | --- |
| `type` | `started`, `progress` or `finished` |
| `instance`, `plan_id`, `plan_name`, `repo_id` | which Backrest instance, plan and repository |
| `device_id` | the plan's device in Home Assistant (for `device_attr`) |
| `operation_id`, `started` | the backup run and when it started |
| `progress`, `previous_progress` | percent done now and at the previous update (`progress` is empty when finished) |
| `bytes_done`, `total_bytes`, `files_done`, `total_files` | restic's progress counters, when known |
| `result` | `finished` only: `success`, `warning`, `error`, `cancelled` or `unknown` |
| `ended`, `duration`, `data_added`, `error` | `finished` only: end time, seconds, bytes added, error message |

`progress` events come with each update in which the percentage changed (once a minute). A backup that is already running when Home Assistant starts sends `started` again.

Show a running backup as a notification that updates in steps of 10 %:

```yaml
alias: "Backups - Progress notification"
triggers:
  - trigger: event
    event_type: backrest_backup
conditions:
  - condition: template
    value_template: >-
      {{ trigger.event.data.type != 'progress'
         or (trigger.event.data.progress // 10)
            != ((trigger.event.data.previous_progress or 0) // 10) }}
actions:
  - action: notify.notify
    data:
      title: "Backup {{ trigger.event.data.plan_name }}"
      message: >-
        {{ trigger.event.data.result if trigger.event.data.type == 'finished'
           else (trigger.event.data.progress | round(0) ~ ' %') }}
```

## Known limitations

- Progress is refreshed once a minute; live progress via Backrest's event stream is planned.
- Backrest has no read-only API users. The Home Assistant user can do everything in Backrest, although the integration itself only reads.
- *Snapshots* comes from Backrest's own summary and can stay at 0 until Backrest has indexed the repository.
- Only plans of the instance itself are shown, not plans of other instances synced to it.
- Custom brand images need Home Assistant 2026.3 or newer; older versions show a placeholder icon.

## Troubleshooting

- **Cannot connect**: open the URL from the Home Assistant host (`curl -X POST <url>/v1.Backrest/GetConfig -H 'Content-Type: application/json' -d '{}'`). A firewall between VLANs or a reverse proxy login page are the usual causes.
- **Invalid authentication**: check the user in Backrest under *Settings → Users*. Home Assistant asks for new credentials by itself when they stop working.
- **Values look wrong**: download the diagnostics from the integration page and open an [issue](https://github.com/fmeesters/ha-backrest/issues). Turn on debug logging for `custom_components.backrest` for more detail.

## Removing the integration

1. Go to **Settings → Devices & services → Backrest**, open the menu of each instance and choose **Delete**.
2. Remove the repository in HACS (or delete `custom_components/backrest`) and restart Home Assistant.
3. Optionally delete the Home Assistant user in Backrest.

## Diagnostics

The diagnostics download leaves out the password, user name, URL, repository URIs and backup paths.

## Quality

The integration follows the Home Assistant [Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/) and aims at Gold: config flow with reauth and reconfigure, `runtime_data`, a data update coordinator, translated entities, states, icons and errors, devices with dynamic add and stale-device removal, diagnostics, strict typing and tests with more than 95 % coverage. Discovery does not apply: Backrest does not announce itself on the network.

## Releases

Push a tag that matches the version in `manifest.json` (for example `v0.1.2`) and the release workflow publishes a GitHub release; a release made by hand in the GitHub UI with such a tag works too. HACS then offers it as an update.

## Development

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
ruff format . && ruff check . && mypy custom_components && pytest --cov
```

## License

MIT
