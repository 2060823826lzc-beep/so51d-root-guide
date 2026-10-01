// Modified for Xperia Experimental Toolbox diagnostic logging; 2026-09-29. See native/MODIFICATIONS.md.
#ifndef GHOSTLOCK_RACE_DIAGNOSTICS_HPP
#define GHOSTLOCK_RACE_DIAGNOSTICS_HPP

#include "support/native_resource.hpp"
#include <cerrno>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <sys/syscall.h>
#include <unistd.h>

namespace ghostlock::diagnostics {
    struct ThreadIdentity {
        long tid;
        unsigned long long handle;
        int state;
    };

    inline ThreadIdentity identity(const support::PthreadOwner &owner) noexcept {
        long tid = -1;
#if defined(__ANDROID__)
        if (owner.joinable()) tid = static_cast<long>(pthread_gettid_np(owner.native_handle()));
#endif
        const pthread_t handle = owner.native_handle();
        uintptr_t raw_handle = 0;
        static_assert(sizeof(handle) <= sizeof(raw_handle));
        memcpy(&raw_handle, &handle, sizeof(handle));
        return {tid, static_cast<unsigned long long>(raw_handle),
                static_cast<int>(owner.state())};
    }

    inline long long monotonic_ms() noexcept {
        timespec stamp{};
        if (clock_gettime(CLOCK_MONOTONIC, &stamp) != 0) return -1;
        return static_cast<long long>(stamp.tv_sec) * 1000LL + stamp.tv_nsec / 1000000LL;
    }

    // Called only at existing stage boundaries, never from a race worker loop.
    [[gnu::noinline]] inline void stage(const char *label) noexcept {
        const int saved_errno = errno;
        fprintf(stderr, "[DIAG] stage mono_ms=%lld pid=%ld tid=%ld label=%s\n",
                monotonic_ms(), static_cast<long>(getpid()), syscall(SYS_gettid), label);
        errno = saved_errno;
    }

    [[gnu::noinline]] inline void reset(bool waiter, bool owner, bool consumer) noexcept {
        const int saved_errno = errno;
        fprintf(stderr, "[DIAG] reset mono_ms=%lld pid=%ld live_joinable=%d/%d/%d\n",
                monotonic_ms(), static_cast<long>(getpid()),
                static_cast<int>(waiter), static_cast<int>(owner), static_cast<int>(consumer));
        errno = saved_errno;
    }

    // Emission occurs after all three original join calls; no logging between joins.
    [[gnu::noinline]] inline void join(const ThreadIdentity &waiter,
                                     const ThreadIdentity &owner,
                                     const ThreadIdentity &consumer,
                                     int32_t waiter_rc, int32_t owner_rc, int32_t consumer_rc,
                                     bool waiter_live, bool owner_live, bool consumer_live) noexcept {
        const int saved_errno = errno;
        fprintf(stderr,
                "[DIAG] join mono_ms=%lld pid=%ld waiter_tid=%ld owner_tid=%ld consumer_tid=%ld "
                "handles=%llu/%llu/%llu states_before=%d/%d/%d "
                "rc=%d/%d/%d rc_all_zero=%d remaining_joinable=%d/%d/%d\n",
                monotonic_ms(), static_cast<long>(getpid()), waiter.tid, owner.tid, consumer.tid,
                waiter.handle, owner.handle, consumer.handle, waiter.state, owner.state, consumer.state,
                waiter_rc, owner_rc, consumer_rc,
                static_cast<int>(waiter_rc == 0 && owner_rc == 0 && consumer_rc == 0),
                static_cast<int>(waiter_live), static_cast<int>(owner_live), static_cast<int>(consumer_live));
        errno = saved_errno;
    }
}
#endif
