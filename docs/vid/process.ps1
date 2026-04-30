$fps = 15
$width = 718
$dither = "bayer:bayer_scale=5"
$exts = @("mp4","mov","mkv","avi","webm","m4v","3gp","mpg","mpeg","flv","wmv")

Get-ChildItem -File | Where-Object {
    $exts -contains ($_.Extension.TrimStart('.').ToLower())
} | ForEach-Object {
    $inputfile = $_.FullName
    $base = [System.IO.Path]::GetFileNameWithoutExtension($inputfile)
    $palette = "$base-palette.png"
    $outgif = "$base.gif"

    if ($width -eq 0) { $scale = 'scale=iw:-1:flags=lanczos' }
    else { $scale = "scale=${width}:-1:flags=lanczos" }

    Write-Host "processing... $inputfile -> $outgif"

    & ffmpeg -y -i $inputfile -vf "fps=$fps,$scale,palettegen=stats_mode=diff" -q:v 2 $palette

    if (-not (Test-Path $palette)) {
        Write-Warning "palette generation failed for $inputfile. skipping"
        return
    }

    $gifFilter = "fps=$fps,$scale[x];[x][1:v]paletteuse=dither=$dither"
    & ffmpeg -y -i $inputfile -i $palette -filter_complex $gifFilter -loop 0 $outgif

    Remove-Item $palette -ErrorAction SilentlyContinue
    Write-Host "finished... $outgif"
}
