#!/bin/zsh
script_dir="${0:A:h}"

if [[ -n "$1" ]]; then
  source_path="$1"
else
  source_path=$(osascript -e 'POSIX path of (choose folder with prompt "选择一集 Bilibili 下载视频的文件夹")')
  if (( $? != 0 )); then
    print '已取消选择。'
    exit 0
  fi
fi

python3 "$script_dir/bilicache_converter.py" "$source_path"
result=$?
print
if (( result == 0 )); then
  print '转换完成。按回车关闭窗口。'
else
  print '转换未完成。请查看上面的错误信息，按回车关闭窗口。'
fi
read -r
exit $result
