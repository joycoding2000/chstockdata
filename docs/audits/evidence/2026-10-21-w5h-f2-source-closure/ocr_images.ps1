param([Parameter(Mandatory=$true)][string]$Plan, [string]$Language='zh-Hans-CN')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null
$taskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and
    $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await-Result($operation, [Type]$resultType) {
    $task = $taskMethod.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.GetAwaiter().GetResult()
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($Language))
if ($null -eq $engine) { throw 'Existing Chinese OCR unavailable; no install or network fallback' }
$items = Get-Content -LiteralPath $Plan -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($item in $items) {
    if (Test-Path -LiteralPath $item.output) { continue }
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $file = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($item.image)) ([Windows.Storage.StorageFile])
    $stream = Await-Result ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $lines = @($result.Lines | ForEach-Object {
        @{ text=$_.Text; words=@($_.Words | ForEach-Object {
            @{text=$_.Text; x=$_.BoundingRect.X; y=$_.BoundingRect.Y;
              width=$_.BoundingRect.Width; height=$_.BoundingRect.Height}
        }) }
    })
    $clock.Stop()
    $output = @{id=$item.id; physical_page=$item.physical_page; source_sha256=$item.source_sha256;
        image_sha256=(Get-FileHash -LiteralPath $item.image -Algorithm SHA256).Hash.ToLowerInvariant();
        engine=('Windows.Media.Ocr existing '+$Language); maximum_image_dimension=[Windows.Media.Ocr.OcrEngine]::MaxImageDimension;
        pixel_width=$bitmap.PixelWidth; pixel_height=$bitmap.PixelHeight;
        machine_seconds=$clock.Elapsed.TotalSeconds; text=$result.Text; lines=$lines; pit_qualified=$false}
    [IO.File]::WriteAllText($item.output, ($output | ConvertTo-Json -Depth 9), [Text.UTF8Encoding]::new($false))
    $bitmap.Dispose()
    $stream.Dispose()
    Write-Output ($item.id + ':' + $item.physical_page + ' OCR ' + $lines.Count + ' lines')
}
