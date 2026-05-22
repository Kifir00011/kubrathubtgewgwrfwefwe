// Пример: dotnet run -- https://xxxx.loca.lt C:\path\to\file.zip
// Локально: dotnet run -- http://127.0.0.1:3847 C:\path\to\file.zip

using FileTunnel;

if (args.Length < 2)
{
    Console.WriteLine("Usage: ExampleUpload <baseUrl> <filePath>");
    Console.WriteLine("  ExampleUpload http://127.0.0.1:3847 C:\\test.bin");
    return 1;
}

var baseUrl = args[0];
var filePath = args[1];

using var client = new FileTunnelClient(baseUrl);

var info = await client.GetInfoAsync();
Console.WriteLine($"API v{info.Version} @ {info.BaseUrl}");

Console.WriteLine("Upload (multipart)...");
var multipart = await client.UploadFileAsync(filePath);
foreach (var f in multipart.Files)
    Console.WriteLine($"  -> {f.Name} ({f.Size} bytes)  {f.DownloadUrl}");

Console.WriteLine("Upload (binary API)...");
var binary = await client.UploadFileBinaryAsync(filePath);
foreach (var f in binary.Files)
    Console.WriteLine($"  -> {f.Name}  {f.DownloadUrl}");

Console.WriteLine("Files on server:");
foreach (var f in await client.ListFilesAsync())
    Console.WriteLine($"  {f.Name}  {f.Size} bytes  {f.DownloadUrl}");

return 0;
