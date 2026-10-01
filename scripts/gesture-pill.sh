#!/system/bin/sh
# Persistent SystemUI color overlay. Never changes navigation geometry or mode.
ACTION=${1:-status}
OVERLAY=android:CodexGesturePill
TARGET=com.android.systemui
DARK_RES=$TARGET:color/navigation_bar_home_handle_dark_color
LIGHT_RES=$TARGET:color/navigation_bar_home_handle_light_color
HELPER=${2:-$(dirname "$0")/gesture-pill-overlay.jar}
fail() { echo "失败：$*" >&2; exit 1; }
lookup() { cmd overlay lookup --user 0 "$TARGET" "$1"; }
read_list() { OVERLAY_LIST=$(cmd overlay list --user 0 "$TARGET"); }
is_enabled() { printf '%s\n' "$OVERLAY_LIST" | grep -F -x "[x] $1" >/dev/null; }
is_present() { printf '%s\n' "$OVERLAY_LIST" | grep -F -x -e "[x] $1" -e "[ ] $1" -e "--- $1" >/dev/null; }
is_transparent() { case "$1" in '#0'|'#00000000') return 0;; *) return 1;; esac; }
case "$ACTION" in hide|show|status) ;; *) fail '用法：sh gesture-pill.sh hide|show|status [helper.jar]';; esac
[ "$(am get-current-user)" = 0 ] || fail '请切换到机主用户。'
read_list || fail '无法读取资源覆盖。'
DARK_COLOR=$(lookup "$DARK_RES") || fail '找不到深色手势条资源。'
LIGHT_COLOR=$(lookup "$LIGHT_RES") || fail '找不到浅色手势条资源。'
if [ "$ACTION" = status ]; then
    echo "机型：$(getprop ro.product.model)"
    echo "导航模式：$(settings get secure navigation_mode)（2 表示手势导航）"
    printf '%s\n' "$OVERLAY_LIST" | grep -E 'android:CodexGesturePill|com.android.shell:CodexGesture' || true
    echo "深色小白条颜色：$DARK_COLOR"
    echo "浅色小白条颜色：$LIGHT_COLOR"
    exit 0
fi
[ "$(id -u)" = 0 ] || fail '修改时需要 Root。'
[ -r "$HELPER" ] || fail '缺少 gesture-pill-overlay.jar。'
if [ "$ACTION" = hide ]; then
    [ "$(settings get secure navigation_mode)" = 2 ] || fail '当前不是手势导航。'
    if is_enabled "$OVERLAY" && is_transparent "$DARK_COLOR" && is_transparent "$LIGHT_COLOR"; then
        echo '持久隐藏配置已经生效，无需重复修改。'
        exit 0
    fi
    CLASSPATH="$HELPER" app_process /system/bin GesturePillOverlay hide || fail '保存持久配置失败。'
    read_list || fail '无法读取修改后的状态。'
    if ! is_enabled "$OVERLAY" || ! is_transparent "$(lookup "$DARK_RES")" || ! is_transparent "$(lookup "$LIGHT_RES")"; then
        CLASSPATH="$HELPER" app_process /system/bin GesturePillOverlay show >/dev/null 2>&1
        fail '颜色验证失败，已尝试撤销新增覆盖。'
    fi
else
    if is_present "$OVERLAY"; then
        CLASSPATH="$HELPER" app_process /system/bin GesturePillOverlay show || fail '移除持久配置失败。'
    fi
fi
# Retire only this tool's old temporary overlays if still present.
for legacy in com.android.shell:CodexGestureDark com.android.shell:CodexGestureLight; do
    if is_enabled "$legacy"; then
        cmd overlay disable --user 0 "$legacy" || fail '停用旧临时配置失败。'
    fi
done
read_list || fail '无法读取最终覆盖状态。'
if [ "$ACTION" = show ] && is_enabled "$OVERLAY"; then
    fail '覆盖仍然启用，未确认恢复。'
fi
echo "深色资源：$(lookup "$DARK_RES")；浅色资源：$(lookup "$LIGHT_RES")"
sync
echo '配置已保存，正在刷新系统界面。'
killall com.android.systemui || fail '配置已保存，但系统界面刷新失败。'
echo '完成。'
