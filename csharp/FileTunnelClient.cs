using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace FileTunnel;

/// <summary>
/// HTTP API клиент для file-tunnel-server (python server.py).
/// </summary>
public sealed class FileTunnelClient : IDisposable
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    private readonly HttpClient _http;
    private readonly string _baseUrl;

    public FileTunnelClient(string baseUrl, HttpMessageHandler? handler = null, TimeSpan? timeout = null)
    {
        if (string.IsNullOrWhiteSpace(baseUrl))
            throw new ArgumentException("Base URL is required", nameof(baseUrl));

        _baseUrl = baseUrl.TrimEnd('/');
        _http = handler is null ? new HttpClient() : new HttpClient(handler);
        _http.Timeout = timeout ?? TimeSpan.FromHours(24);
        _http.DefaultRequestHeaders.Add("X-Base-Url", _baseUrl);
        _http.DefaultRequestHeaders.UserAgent.ParseAdd("FileTunnelClient/1.0");
    }

    public Uri BaseUri => new(_baseUrl);

    public async Task<ApiInfoResponse> GetInfoAsync(CancellationToken cancellationToken = default)
    {
        return await GetJsonAsync<ApiInfoResponse>("/api/info", cancellationToken)
            ?? throw new InvalidOperationException("Empty /api/info response");
    }

    public async Task<IReadOnlyList<RemoteFileInfo>> ListFilesAsync(CancellationToken cancellationToken = default)
    {
        var response = await GetJsonAsync<FileListResponse>("/api/files", cancellationToken)
            ?? throw new InvalidOperationException("Empty /api/files response");
        return response.Files;
    }

    /// <summary>
    /// Multipart upload (поля files / file).
    /// </summary>
    public async Task<UploadResponse> UploadFileAsync(
        string localPath,
        string? formFieldName = null,
        CancellationToken cancellationToken = default)
    {
        if (!File.Exists(localPath))
            throw new FileNotFoundException("File not found", localPath);

        var field = string.IsNullOrWhiteSpace(formFieldName) ? "files" : formFieldName;
        await using var stream = File.OpenRead(localPath);
        using var content = new MultipartFormDataContent();
        var part = new StreamContent(stream);
        part.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        content.Add(part, field, Path.GetFileName(localPath));
        return await PostUploadAsync("/api/upload", content, cancellationToken);
    }

    /// <summary>
    /// Сырой PUT/POST — тело файла + X-Filename.
    /// </summary>
    public async Task<UploadResponse> UploadFileBinaryAsync(
        string localPath,
        CancellationToken cancellationToken = default)
    {
        if (!File.Exists(localPath))
            throw new FileNotFoundException("File not found", localPath);

        var fileName = Path.GetFileName(localPath);
        await using var stream = File.OpenRead(localPath);
        using var content = new StreamContent(stream);
        content.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        using var request = new HttpRequestMessage(HttpMethod.Put, $"{_baseUrl}/api/upload/binary");
        request.Content = content;
        request.Headers.Add("X-Filename", fileName);

        using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
            throw new HttpRequestException($"Upload failed {(int)response.StatusCode}: {body}");

        return JsonSerializer.Deserialize<UploadResponse>(body, JsonOptions)
            ?? throw new InvalidOperationException("Invalid upload response");
    }

    public async Task DownloadFileAsync(
        string remoteName,
        string saveToPath,
        CancellationToken cancellationToken = default)
    {
        var url = $"{_baseUrl}/api/download/{Uri.EscapeDataString(remoteName)}";
        using var response = await _http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();

        var dir = Path.GetDirectoryName(saveToPath);
        if (!string.IsNullOrEmpty(dir))
            Directory.CreateDirectory(dir);

        await using var input = await response.Content.ReadAsStreamAsync(cancellationToken);
        await using var output = File.Create(saveToPath);
        await input.CopyToAsync(output, cancellationToken);
    }

    public async Task<bool> DeleteFileAsync(string remoteName, CancellationToken cancellationToken = default)
    {
        var url = $"{_baseUrl}/api/files/{Uri.EscapeDataString(remoteName)}";
        using var response = await _http.DeleteAsync(url, cancellationToken);
        return response.IsSuccessStatusCode;
    }

    private async Task<UploadResponse> PostUploadAsync(
        string path,
        HttpContent content,
        CancellationToken cancellationToken)
    {
        using var response = await _http.PostAsync($"{_baseUrl}{path}", content, cancellationToken);
        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
            throw new HttpRequestException($"Upload failed {(int)response.StatusCode}: {body}");

        return JsonSerializer.Deserialize<UploadResponse>(body, JsonOptions)
            ?? throw new InvalidOperationException("Invalid upload response");
    }

    private async Task<T?> GetJsonAsync<T>(string path, CancellationToken cancellationToken)
    {
        return await _http.GetFromJsonAsync<T>($"{_baseUrl}{path}", JsonOptions, cancellationToken);
    }

    public void Dispose() => _http.Dispose();
}

public sealed class ApiInfoResponse
{
    public string Version { get; set; } = "";
    public string BaseUrl { get; set; } = "";
}

public sealed class FileListResponse
{
    public bool Ok { get; set; }
    public int Count { get; set; }
    public List<RemoteFileInfo> Files { get; set; } = new();
}

public sealed class RemoteFileInfo
{
    public string Name { get; set; } = "";
    public long Size { get; set; }
    public string Mtime { get; set; } = "";
    public string DownloadUrl { get; set; } = "";
    public string ApiDownloadUrl { get; set; } = "";
}

public sealed class UploadResponse
{
    public bool Ok { get; set; }
    public List<UploadedFileInfo> Files { get; set; } = new();
}

public sealed class UploadedFileInfo
{
    public string Name { get; set; } = "";
    [JsonPropertyName("originalName")]
    public string OriginalName { get; set; } = "";
    public long Size { get; set; }
    public string Url { get; set; } = "";
    public string DownloadUrl { get; set; } = "";
}
