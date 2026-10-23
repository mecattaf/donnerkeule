/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TBV_FRAMEWORK_RING_H
#define TBV_FRAMEWORK_RING_H

/* Private NHI descriptor ABI, audited against these exact stable releases.
 * linux/version.h must be included first. A new release needs a source/layout
 * audit and a matching-kernel build before joining this list. See
 * docs/framework-desktop-kernels.md. This is not hardware qualification. */
#if defined(CONFIG_X86_64) && \
	(LINUX_VERSION_CODE == KERNEL_VERSION(7, 2, 6) || \
	 LINUX_VERSION_CODE == KERNEL_VERSION(7, 2, 10) || \
	 LINUX_VERSION_CODE == KERNEL_VERSION(7, 2, 12) || \
	 LINUX_VERSION_CODE == KERNEL_VERSION(7, 3, 0))
#define TBV_FRAMEWORK_RING_ABI 1
#else
#define TBV_FRAMEWORK_RING_ABI 0
#endif

/* Linux 7.3 added rings owned by a polling caller. Do not publish an IRQ
 * descriptor group or schedule the ordinary worker for those rings. Probe the
 * header flag so a backport receives the same ownership protection. */
#ifdef RING_FLAG_NO_INTERRUPT
#define TBV_FRAMEWORK_RING_NO_INTERRUPT(flags) ((flags) & RING_FLAG_NO_INTERRUPT)
#else
#define TBV_FRAMEWORK_RING_NO_INTERRUPT(flags) 0
#endif

#endif
