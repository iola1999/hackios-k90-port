#!/bin/bash
# sheets.sh RUN_DIR: full-size PNG per raw screenshot (raw removed), and contact sheets of 8x2 thumbnails.
set -e
cd "$1"
mkdir -p png thumbs
for raw in shot-*.raw; do
	[ -e "$raw" ] || continue
	base=${raw%.raw}
	ffmpeg -v error -y -f rawvideo -pix_fmt bgra -s 1156x2510 -i "$raw" "png/$base.png" &&
	ffmpeg -v error -y -i "png/$base.png" -vf "scale=231:-1,drawtext=text='${base#shot-}':x=4:y=4:fontsize=22:fontcolor=red:box=1" "thumbs/$base.png" 2>/dev/null ||
	ffmpeg -v error -y -i "png/$base.png" -vf "scale=231:-1" "thumbs/$base.png"
	rm -f "$raw"
done
ls thumbs/*.png | sort > thumbs/list.txt
n=0
split -l 16 thumbs/list.txt thumbs/part-
for part in thumbs/part-*; do
	n=$((n+1))
	args=(); for f in $(cat $part); do args+=(-i "$f"); done
	count=$(wc -l < $part)
	ffmpeg -v error -y "${args[@]}" -filter_complex "$(for i in $(seq 0 $((count-1))); do printf '[%d:v]' $i; done)xstack=inputs=$count:layout=$(python3 -c "
c=$count
print('|'.join(f'{(i%8)*231}_{(i//8)*502}' for i in range(c)))"):fill=black" "sheet-$n.png" 2>/dev/null || true
	rm -f $part
done
ls sheet-*.png
