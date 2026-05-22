# File Tunnel API

Базовый URL: `http://127.0.0.1:3847` или публичный туннель **cloudflared**: `https://xxxx.trycloudflare.com` (из консоли при `python server.py`).

Специальных заголовков для обхода блокировок не нужно.

## Endpoints

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/info` | Описание API |
| GET | `/api/health` | Проверка сервера |
| GET | `/api/files` | Список файлов |
| POST | `/api/upload` | Multipart: поля `files` или `file` |
| PUT | `/api/upload/binary` | Сырое тело + заголовок `X-Filename` |
| GET | `/api/download/{name}` | Скачать файл |
| DELETE | `/api/files/{name}` | Удалить файл |

## Upload (multipart) — для C#

```csharp
using var client = new FileTunnelClient("http://127.0.0.1:3847");
var result = await client.UploadFileAsync(@"C:\data\report.zip");
Console.WriteLine(result.Files[0].DownloadUrl);
```

Поле формы: **`files`** (или **`file`**).

## Upload (binary) — для C#

```csharp
var result = await client.UploadFileBinaryAsync(@"C:\data\report.zip");
```

HTTP:
```
PUT /api/upload/binary
Content-Type: application/octet-stream
X-Filename: report.zip

<сырые байты файла>
```

## Download

```csharp
await client.DownloadFileAsync(remoteName: "1716384000000-report.zip", @"C:\out\report.zip");
```

## List

```csharp
var files = await client.ListFilesAsync();
```

## Ответ upload

```json
{
  "ok": true,
  "files": [
    {
      "name": "1716384000000-report.zip",
      "originalName": "report.zip",
      "size": 12345,
      "url": "/download/1716384000000-report.zip",
      "downloadUrl": "http://127.0.0.1:3847/download/1716384000000-report.zip"
    }
  ]
}
```

## Пример проекта

```bat
cd csharp
dotnet run --project ExampleUpload.csproj -- http://127.0.0.1:3847 C:\path\file.bin
```

Скопируй `FileTunnelClient.cs` в свой C# проект (namespace `FileTunnel`).
