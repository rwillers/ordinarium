(() => {
	const menuSelector = '[data-dropdown-menu]'
	const toggleSelector = '[data-dropdown-toggle]'
	const panelSelector = '[data-dropdown-panel]'
	const itemSelector = '.dropdown-menu-item, [data-dropdown-item]'
	let activeMenu = null
	let activeToggle = null
	let menuIdCounter = 0

	const listMenus = () => Array.from(document.querySelectorAll(menuSelector))

	const ensureMenuId = (menu) => {
		if (!menu) {
			return ''
		}
		if (!menu.dataset.dropdownId) {
			menuIdCounter += 1
			menu.dataset.dropdownId = `dropdown-menu-${menuIdCounter}`
		}
		return menu.dataset.dropdownId
	}

	const getPanelOwner = (panel) => {
		const ownerId = panel?.dataset.dropdownOwnerId
		if (!ownerId) {
			return null
		}
		return listMenus().find((menu) => menu.dataset.dropdownId === ownerId) || null
	}

	const getMenuItems = (menu) => {
		const panel = getPanel(menu)
		if (!panel) {
			return []
		}
		return Array.from(panel.querySelectorAll(itemSelector))
	}

	const getPanel = (menu) => {
		if (!menu) {
			return null
		}
		const attachedPanel = menu.querySelector(panelSelector)
		if (attachedPanel) {
			return attachedPanel
		}
		const menuId = menu.dataset.dropdownId
		if (!menuId) {
			return null
		}
		return Array.from(document.querySelectorAll(`${panelSelector}[data-dropdown-owner-id]`)).find(
			(panel) => panel.dataset.dropdownOwnerId === menuId
		) || null
	}

	const resetLayeredPosition = (panel) => {
		if (!panel) {
			return
		}
		panel.classList.remove('is-layered')
		panel.style.removeProperty('left')
		panel.style.removeProperty('top')
	}

	const syncPanelVariables = (menu, panel) => {
		if (!menu || !panel) {
			return
		}
		const computed = window.getComputedStyle(menu)
		;['--dropdown-panel-min-width', '--dropdown-item-font-size'].forEach((property) => {
			const value = computed.getPropertyValue(property).trim()
			if (value) {
				panel.style.setProperty(property, value)
				return
			}
			panel.style.removeProperty(property)
		})
	}

	const restorePanel = (menu) => {
		const panel = getPanel(menu)
		if (!panel || !menu) {
			return
		}
		panel.dataset.dropdownOwnerId = ''
		if (panel.parentElement !== menu) {
			menu.appendChild(panel)
		}
	}

	const setRowMenuState = (menu, isOpen) => {
		const row = menu?.closest('.plan-row')
		if (row) {
			row.classList.toggle('is-menu-open', isOpen)
		}
	}

	const clearLayeredPosition = (menu) => {
		const panel = getPanel(menu)
		if (!panel) {
			return
		}
		resetLayeredPosition(panel)
		restorePanel(menu)
	}

	const movePanelToLayer = (menu) => {
		const panel = getPanel(menu)
		if (!panel || !menu) {
			return null
		}
		ensureMenuId(menu)
		panel.dataset.dropdownOwnerId = menu.dataset.dropdownId
		panel.classList.toggle('is-shared-table-panel', menu.classList.contains('shared-table-menu'))
		syncPanelVariables(menu, panel)
		if (panel.parentElement !== document.body) {
			document.body.appendChild(panel)
		}
		return panel
	}

	const getMenuFromNode = (node) => {
		if (!(node instanceof Element)) {
			return null
		}
		const menu = node.closest(menuSelector)
		if (menu) {
			return menu
		}
		const panel = node.closest(panelSelector)
		if (!panel) {
			return null
		}
		return getPanelOwner(panel)
	}

	const positionLayeredMenu = (menu, toggle) => {
		if (!menu || !toggle) {
			return
		}
		if (menu.dataset.dropdownLayered !== 'true') {
			clearLayeredPosition(menu)
			return
		}
		const panel = movePanelToLayer(menu)
		if (!panel) {
			return
		}
		resetLayeredPosition(panel)
		panel.classList.add('is-layered')
		const toggleRect = toggle.getBoundingClientRect()
		const panelWidth = panel.offsetWidth || 184
		const panelHeight = panel.offsetHeight || 160
		const viewportPadding = 8
		const openOffset = 4
		let top = toggleRect.bottom + openOffset
		const canOpenUp = toggleRect.top - panelHeight - openOffset >= viewportPadding
		if (top + panelHeight + viewportPadding > window.innerHeight && canOpenUp) {
			top = toggleRect.top - panelHeight - openOffset
		}
		let left = toggleRect.right - panelWidth
		left = Math.max(viewportPadding, Math.min(left, window.innerWidth - panelWidth - viewportPadding))
		panel.style.left = `${Math.round(left)}px`
		panel.style.top = `${Math.round(top)}px`
	}

	const closeMenu = (menu) => {
		if (!menu) {
			return
		}
		menu.classList.remove('is-open')
		clearLayeredPosition(menu)
		setRowMenuState(menu, false)
		const toggle = menu.querySelector(toggleSelector)
		if (toggle) {
			toggle.setAttribute('aria-expanded', 'false')
		}
		if (activeMenu === menu) {
			activeMenu = null
			activeToggle = null
		}
	}

	const closeMenus = ({ exceptMenu = null, group = null, restoreFocus = false } = {}) => {
		listMenus().forEach((menu) => {
			if (menu === exceptMenu) {
				return
			}
			if (group && menu.dataset.dropdownGroup !== group) {
				return
			}
			closeMenu(menu)
		})
		if (!exceptMenu) {
			if (restoreFocus && activeToggle) {
				activeToggle.focus()
			}
			activeMenu = null
			activeToggle = null
		}
	}

	const toggleMenu = (menu, toggle) => {
		if (!menu || !toggle) {
			return
		}
		const group = menu.dataset.dropdownGroup || null
		const isOpen = !menu.classList.contains('is-open')
		closeMenus({ exceptMenu: menu, group })
		menu.classList.toggle('is-open', isOpen)
		toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false')
		setRowMenuState(menu, isOpen)
		if (isOpen) {
			positionLayeredMenu(menu, toggle)
			activeMenu = menu
			activeToggle = toggle
			const items = getMenuItems(menu)
			if (items[0]) {
				items[0].focus()
			}
			return
		}
		clearLayeredPosition(menu)
		if (activeMenu === menu) {
			activeMenu = null
			activeToggle = null
		}
	}

	document.addEventListener('click', (event) => {
		const target = event.target instanceof Element ? event.target : null
		if (!target) {
			return
		}
		const toggle = target.closest(toggleSelector)
		if (toggle) {
			const menu = toggle.closest(menuSelector)
			if (!menu) {
				return
			}
			event.preventDefault()
			event.stopPropagation()
			toggleMenu(menu, toggle)
			return
		}
		const item = target.closest(itemSelector)
		if (item) {
			const menu = getMenuFromNode(item)
			if (menu) {
				const group = menu.dataset.dropdownGroup || null
				closeMenus({ group })
			}
			return
		}
		if (!getMenuFromNode(target)) {
			closeMenus()
		}
	})

	window.addEventListener('resize', () => {
		closeMenus()
	})

	window.addEventListener('scroll', () => {
		closeMenus()
	}, true)

	document.addEventListener('keydown', (event) => {
		if (event.key === 'Escape') {
			const hasOpenMenu = Boolean(activeMenu || document.querySelector(`${menuSelector}.is-open`))
			if (!hasOpenMenu) {
				return
			}
			event.preventDefault()
			closeMenus({ restoreFocus: true })
			return
		}
		if (event.key !== 'Tab' || !activeMenu) {
			return
		}
		const items = getMenuItems(activeMenu)
		if (!items.length) {
			event.preventDefault()
			return
		}
		const firstItem = items[0]
		const lastItem = items[items.length - 1]
		if (event.shiftKey && document.activeElement === firstItem) {
			event.preventDefault()
			lastItem.focus()
			return
		}
		if (!event.shiftKey && document.activeElement === lastItem) {
			event.preventDefault()
			firstItem.focus()
		}
	})

	window.dropdownMenus = {
		closeAll: () => closeMenus(),
		closeGroup: (group) => {
			if (!group) {
				closeMenus()
				return
			}
			closeMenus({ group })
		}
	}
})()
