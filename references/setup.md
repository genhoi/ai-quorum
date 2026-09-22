# Установка, ключи, настройки

Скилл — каталог `ai-quorum/`. Нужны `bash`, `git`, `python3` (3.10+), `timeout` (coreutils).
Бэкенды необязательны: совет работает с любыми двумя, но смысл в разных семействах моделей.

## 1. Подключить скилл

```bash
git clone https://github.com/genhoi/ai-quorum ~/projects/genhoi/ai-quorum
ln -sfn ~/projects/genhoi/ai-quorum ~/.claude/skills/quorum     # Claude Code
mkdir -p ~/.agents/skills ~/.codex/skills ~/.grok/skills
ln -sfn ~/projects/genhoi/ai-quorum ~/.agents/skills/quorum     # kimi, gemini, copilot
ln -sfn ~/projects/genhoi/ai-quorum ~/.codex/skills/quorum      # codex
ln -sfn ~/projects/genhoi/ai-quorum ~/.grok/skills/quorum       # grok
ln -sfn ~/projects/genhoi/ai-quorum/bin/quorum ~/.local/bin/quorum
```

## 2. Ключи и логины бэкендов

| Бэкенд | Что нужно | Где взять |
|---|---|---|
| codex | codex CLI + `codex login` или `codex login --device-auth` | подписка ChatGPT |
| grok | grok CLI + вход (`grok`, затем `/login`) | подписка xAI |
| glm | `~/.claude/zai_api_key` (одна строка) или `ZAI_API_KEY` | z.ai, GLM Coding Plan |
| kimi | `~/.claude/kimi_api_key` или `KIMI_API_KEY` | kimi.com/code/console (подписка Kimi Code) |
| kimi-cli | kimi-code CLI + `kimi login` | та же подписка, OAuth протухает — запасной путь |
| opus, fable | обычный вход в Claude Code (`claude auth login`) | подписка Claude |

Файл ключа: `printf '%s' 'KEY' > ~/.claude/zai_api_key && chmod 600 ~/.claude/zai_api_key`.
Проверка: `quorum doctor`.

## 3. Кто советует и кто судит

```bash
quorum config                                  # действующие значения и путь к файлу
quorum config set QUORUM_ADVISORS codex,grok,glm
quorum config set QUORUM_JUDGE fable
quorum config set QUORUM_JUDGE_EFFORT high     # судья читает три коротких ответа, high достаточно
quorum config set CODEX_MODEL gpt-6-astra
quorum config set CODEX_EFFORT xhigh
```

Файл: `~/.config/quorum/config.env`. Приоритет: переменная окружения → текущий родительский
тред Codex (только модель и effort, когда скилл запущен из Codex) → файл → значение в
`bin/lib/defaults.sh`. Один прогон: `QUORUM_JUDGE=opus quorum consult ...`, или флаги
`--advisors`, `--judge`.

Судья должен быть из семейства, отличного от советников: иначе он судит «своего». Скилл предупреждает,
но не запрещает. Опровергатель выбирается сам: первый ответивший советник не из семейства
победителя, иначе судья.

## 4. Переменные

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `QUORUM_ADVISORS` | `codex,grok,glm` | советники; `name:variant` запускает один бэкенд дважды |
| `QUORUM_JUDGE` | `fable` | судья (на приёмке не участвует, кроме роли запасного опровергателя) |
| `QUORUM_ADVISOR_EFFORT` / `QUORUM_JUDGE_EFFORT` | `max` / `high` | effort для семейства Claude; codex и grok берут `CODEX_EFFORT` / `GROK_EFFORT` |
| `QUORUM_RETRY` | `1` | повторный круг у судьи после «приемлемого нет»: 0 или 1 |
| `QUORUM_TIMEOUT` / `QUORUM_JUDGE_TIMEOUT` | `3600` / `1500` | секунд на советника или опровергателя / на судью |
| `QUORUM_DEPS` | `copy` | зависимости в снапшоте: copy, hardlink, symlink, none |
| `QUORUM_HOME` | `~/.local/state/quorum` | прогоны, журнал, изолированные конфиги glm и kimi |
| `QUORUM_NO_USAGE` | — | `1` выключает журнал `usage.jsonl` |
| `QUORUM_WAIT_MAX` | `110` | сколько секунд ждёт `quorum wait` без `--max` (меньше лимита Bash в Claude Code) |
| `GLM_MODEL`, `KIMI_MODEL`, `OPUS_MODEL`, `FABLE_MODEL`, `GROK_MODEL`, `CODEX_MODEL` | см. `quorum config` | модели |
| `CLAUDE_BIN`, `CODEX_BIN`, `GROK_BIN`, `KIMI_BIN` | из PATH | пути к бинарникам |

## 5. Профиль проекта

Раздел `## Quorum` (или `## Совет`; старые `## External review` и `## Внешнее ревью` тоже читаются) в `AGENTS.md` или `CLAUDE.md` репозитория подставляется в
каждый бриф: команды тестов, линтера, e2e, что недоступно в снапшоте, известные решения.
Заполнить один раз на проект.
