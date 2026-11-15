# Documentation index

**Read these as web pages, with search and diagrams: https://www.mhraaga.in/docs/index.html**
The pages are built from the Markdown here: `python3 tools/build_docs.py` (needs `pip install markdown pygments`; see the header of that file for the diagram step), then deploy.

Start with the [root README](../README.md), then:

| Doc | For |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | The detailed architecture, step by step, and how Kalkee is (and is not) used |
| [ENGINE.md](ENGINE.md) | Every engine module: compose, ragas, tala, brief, poems, lyrics, physics, GAN, auto-tune |
| [BACKEND.md](BACKEND.md) | handler, studio, team, voice, admin, the tables and the infrastructure |
| [ADMIN.md](ADMIN.md) | The admin dashboard: users, types, columns, cloud cost |
| [API.md](API.md) | Developers who call the API from outside (accounts, endpoints, the score format) |
| [../tool_layer_mhraga/mhraaga-cloud/web/developers.html](../tool_layer_mhraga/mhraaga-cloud/web/developers.html) | The architecture page, published at https://www.mhraaga.in/developers.html |
| [SOUND.md](SOUND.md) | How the instruments are modelled and why it should sound natural, with the measurements |
| [VOICE.md](VOICE.md) | The neural voice, costs and caps |
| [TEAM_AND_PHYSICS.md](TEAM_AND_PHYSICS.md) | Shared studio, Box2D physics, auto-tune, GAN phrases |
| [STUDIO.md](STUDIO.md) | Stories, pravachan, people, rules |
| [AGENTIC_ARCHITECTURE.md](AGENTIC_ARCHITECTURE.md) | The song factory (agents and critics) |
| [DOMAIN.md](DOMAIN.md) | Domain, DNS and HTTPS |
| [components/music-engine.md](components/music-engine.md) | The raga engine package |
| [components/android-app.md](components/android-app.md) | The Flutter Android app |
| [components/music-backend.md](components/music-backend.md), [components/music-mobile.md](components/music-mobile.md) | Earlier prototypes |

The Kalkee orchestrator's documents are in [kalkee/](kalkee/README.md) (moved from its code folders; no code reads them).
