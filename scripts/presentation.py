"""Pure UI decisions, shared by the EXE and backend runtime tests."""
GREEN, AMBER, RED = '#15803d', '#a16207', '#b91c1c'


def root_summary(result):
    if result.get('outcome') == 'cancelled':
        if result.get('display_restore_error'):
            return '已取消，未执行 Root；临时常亮恢复失败，请连接原手机后点击恢复临时设置。', AMBER
        if result.get('display_restored'):
            return '已取消，未执行 Root；原亮屏设置已恢复。', GREEN
        return '已取消，未执行 Root；本次未修改常亮设置。', GREEN
    if result.get('outcome') == 'already_rooted':
        return '手机已具备 Root，本次已跳过激活。', GREEN
    if result.get('root_currently_verified'):
        if result.get('observation_mode') == 'immediate':
            if result.get('immediate_health_passed'):
                return 'Root 已确认，当前状态核验完成。完整记录已保存。', GREEN
            return 'Root 已确认，当前服务检查有异常，请查看日志。', AMBER
        if result.get('all_health_samples_passed'):
            return 'Root 已确认，五分钟采样通过。完整记录已保存。', GREEN
        return 'Root 已确认，五分钟观察有异常或未完整通过。请查看记录。', AMBER
    return result.get('error') or result.get('activation_error') or '未确认 Root 成功。已停止，未自动重试。', RED


def execution_available(state, acknowledged=False):
    if not state or not state.get('connected'):
        return False
    return not state.get('rooted') and not state.get('kernelsu_loaded')
