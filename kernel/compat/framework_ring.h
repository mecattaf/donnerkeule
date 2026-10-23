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
	 LINUX_VERSION_CODE == KERNEL_VERSION(7, 2, 12))
#define TBV_FRAMEWORK_RING_ABI 1
#else
#define TBV_FRAMEWORK_RING_ABI 0
#endif

#endif
