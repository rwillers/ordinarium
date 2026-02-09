const initHeaderMenus = () => {
	const navMenus = Array.from(document.querySelectorAll('header .nav-menu'))
	if (!navMenus.length) {
		return
	}

	const closeMenus = (exceptMenu = null, restoreFocus = false) => {
		navMenus.forEach((menu) => {
			if (menu === exceptMenu) {
				return
			}
			const wasOpen = menu.hasAttribute('open')
			menu.removeAttribute('open')
			if (restoreFocus && wasOpen) {
				const summary = menu.querySelector('summary')
				if (summary instanceof HTMLElement) {
					summary.focus()
				}
			}
		})
	}

	navMenus.forEach((menu) => {
		menu.addEventListener('toggle', () => {
			if (menu.open) {
				closeMenus(menu)
			}
		})

		menu.addEventListener('click', (event) => {
			if (!(event.target instanceof Element)) {
				return
			}
			if (event.target.closest('.nav-dropdown a')) {
				menu.removeAttribute('open')
			}
		})
	})

	document.addEventListener('click', (event) => {
		if (!(event.target instanceof Element)) {
			return
		}
		if (event.target.closest('header .nav-menu')) {
			return
		}
		closeMenus()
	})

	document.addEventListener('keydown', (event) => {
		if (event.key !== 'Escape') {
			return
		}
		closeMenus(null, true)
	})
}

document.addEventListener('DOMContentLoaded', () => {
	initHeaderMenus()
})
