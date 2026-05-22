# File Tunnel Server

Локальный сайт для загрузки и скачивания файлов. Публичный доступ через **Cloudflare Tunnel** (`cloudflared` → `https://xxxx.trycloudflare.com`).

Репозиторий: [github.com/Kifir00011/kubrathubtgewgwrfwefwe](https://github.com/Kifir00011/kubrathubtgewgwrfwefwe)

## GitHub Pages (только UI)

После push включится Pages: `https://kifir00011.github.io/kubrathubtgewgwrfwefwe/`

Там **нет** Python API — укажи в поле «API сервер» URL туннеля или `http://127.0.0.1:3847`.

## Запуск (Windows)

```bat
cd file-tunnel-server
start.bat
```

`start.bat` при необходимости ставит cloudflared через winget.

В консоли появится:

```
=== Public URL (cloudflared) ===
https://xxxx.trycloudflare.com
```

Открой эту ссылку в браузере.

Локально (без интернета): **http://127.0.0.1:3847/**

## Установка cloudflared вручную

```bat
winget install Cloudflare.cloudflared
```

Проверка:

```bat
cloudflared tunnel --url http://127.0.0.1:3847
```

## Возможности

- Загрузка файлов любого размера (на диск)
- Список и скачивание по ссылке
- **REST API для C#** — [API.md](API.md), `csharp/FileTunnelClient.cs`
- Файлы в папке `uploads/`

## C#

```csharp
using var api = new FileTunnel.FileTunnelClient("https://xxxx.trycloudflare.com");
var uploaded = await api.UploadFileAsync(@"C:\myfile.zip");
Console.WriteLine(uploaded.Files[0].DownloadUrl);
```

## Порт

По умолчанию `3847`:

```bat
set PORT=8080
python server.py
```

## Ошибка QUIC / timeout в cloudflared

Если в логе `Failed to dial a quic connection` — сеть или фаервол режет UDP. Скрипт уже запускает с **`--protocol http2`** (TCP).

Если всё равно не коннектится:

- Разреши **cloudflared.exe** в брандмауэре Windows
- Отключи VPN на время теста
- Проверь локально: http://127.0.0.1:3847/ (без туннеля)

## Безопасность

Пока сервер запущен, ссылку может открыть любой. Не оставляй туннель включённым без нужды.
