const sharedTableSorting = () => {
	const tables = Array.from(document.querySelectorAll('.shared-table'))
	if (!tables.length) {
		return
	}
	const compareValues = (aValue, bValue, direction, isDate) => {
		if (isDate) {
			const aTime = aValue ? Date.parse(aValue) : 0
			const bTime = bValue ? Date.parse(bValue) : 0
			return direction === 'asc' ? aTime - bTime : bTime - aTime
		}
		const aText = (aValue || '').toString()
		const bText = (bValue || '').toString()
		return direction === 'asc' ? aText.localeCompare(bText) : bText.localeCompare(aText)
	}

	tables.forEach((table) => {
		const headerCells = Array.from(table.querySelectorAll('th[data-sort-key]'))
		if (!headerCells.length) {
			return
		}
		const getRows = () => Array.from(table.querySelectorAll('tbody tr'))
		const setSortState = (activeHeader, direction) => {
			headerCells.forEach((header) => {
				const isActive = header === activeHeader
				const nextDir = isActive ? direction : 'none'
				header.dataset.sortDir = nextDir
				header.setAttribute(
					'aria-sort',
					isActive ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'
				)
			})
		}
		const sortRows = (header, direction) => {
			const rows = getRows()
			const columnIndex = Array.from(header.parentElement.children).indexOf(header)
			const sortKey = header.dataset.sortKey
			rows.sort((rowA, rowB) => {
				const cellA = rowA.children[columnIndex]
				const cellB = rowB.children[columnIndex]
				const valueA = cellA?.dataset.sortValue || cellA?.textContent?.trim() || ''
				const valueB = cellB?.dataset.sortValue || cellB?.textContent?.trim() || ''
				return compareValues(valueA, valueB, direction, sortKey === 'date')
			})
			const tbody = table.querySelector('tbody')
			rows.forEach((row) => tbody.appendChild(row))
			setSortState(header, direction)
			table.dispatchEvent(new CustomEvent('shared-table:sorted'))
		}
		headerCells.forEach((header) => {
			const button = header.querySelector('button')
			if (!button) {
				return
			}
			button.addEventListener('click', () => {
				const current = header.dataset.sortDir || 'none'
				const next = current === 'asc' ? 'desc' : 'asc'
				sortRows(header, next)
			})
		})
		const initialHeader = headerCells.find(
			(header) => header.dataset.sortDir === 'asc' || header.dataset.sortDir === 'desc'
		)
		if (initialHeader) {
			sortRows(initialHeader, initialHeader.dataset.sortDir)
		}
	})
}

const sharedTablePagination = () => {
	const tables = Array.from(document.querySelectorAll('.shared-table[data-pagination="true"]'))
	if (!tables.length) {
		return
	}
	const parsePageSizeOptions = (value) => {
		const parsed = (value || '')
			.split(',')
			.map((part) => Number.parseInt(part.trim(), 10))
			.filter((size) => Number.isFinite(size) && size > 0)
		return Array.from(new Set(parsed))
	}
	tables.forEach((table, index) => {
		const tbody = table.querySelector('tbody')
		if (!tbody) {
			return
		}
		let pageSizeOptions = parsePageSizeOptions(table.dataset.pageSizeOptions)
		if (!pageSizeOptions.length) {
			pageSizeOptions = [10, 25, 50, 100]
		}
		const configuredPageSize = Number.parseInt(table.dataset.pageSize || '', 10)
		let pageSize = pageSizeOptions.includes(configuredPageSize)
			? configuredPageSize
			: pageSizeOptions[0]
		if (!pageSizeOptions.includes(pageSize)) {
			pageSizeOptions = [...pageSizeOptions, pageSize].sort((a, b) => a - b)
		}
		let currentPage = 1

		const footer = document.createElement('div')
		footer.className = 'shared-table-footer'
		footer.dataset.tablePagination = table.id || `shared-table-${index + 1}`

		const status = document.createElement('p')
		status.className = 'shared-table-footer-status'
		status.setAttribute('aria-live', 'polite')

		const controls = document.createElement('div')
		controls.className = 'shared-table-footer-controls'

		const pageSizeLabel = document.createElement('label')
		pageSizeLabel.className = 'shared-table-page-size'
		pageSizeLabel.htmlFor = `${footer.dataset.tablePagination}-page-size`

		const pageSizeText = document.createElement('span')
		pageSizeText.textContent = 'Rows per page'

		const pageSizeSelect = document.createElement('select')
		pageSizeSelect.id = pageSizeLabel.htmlFor
		pageSizeOptions.forEach((size) => {
			const option = document.createElement('option')
			option.value = String(size)
			option.textContent = String(size)
			pageSizeSelect.appendChild(option)
		})
		pageSizeSelect.value = String(pageSize)

		const pagination = document.createElement('div')
		pagination.className = 'shared-table-pagination'

		pageSizeLabel.append(pageSizeText, pageSizeSelect)
		controls.append(pageSizeLabel, pagination)
		footer.append(status, controls)

		const wrap = table.closest('.shared-table-wrap')
		if (wrap?.parentElement) {
			wrap.insertAdjacentElement('afterend', footer)
		} else {
			table.insertAdjacentElement('afterend', footer)
		}

		const render = () => {
			const rows = Array.from(tbody.querySelectorAll('tr'))
			const totalRecords = rows.length
			if (!totalRecords) {
				status.textContent = 'No records.'
				pageSizeLabel.hidden = true
				pagination.hidden = true
				return
			}
			pageSizeLabel.hidden = false
			const totalPages = Math.max(1, Math.ceil(totalRecords / pageSize))
			if (currentPage > totalPages) {
				currentPage = totalPages
			}
			const startIndex = (currentPage - 1) * pageSize
			const endIndex = Math.min(startIndex + pageSize, totalRecords)
			rows.forEach((row, rowIndex) => {
				row.hidden = rowIndex < startIndex || rowIndex >= endIndex
			})
			status.textContent = `Showing ${startIndex + 1}-${endIndex} of ${totalRecords}`
			pagination.hidden = false

			pagination.replaceChildren()
			const previousButton = document.createElement('button')
			previousButton.type = 'button'
			previousButton.className = 'shared-table-page-button'
			previousButton.textContent = 'Previous'
			previousButton.disabled = currentPage <= 1
			previousButton.addEventListener('click', () => {
				if (currentPage <= 1) {
					return
				}
				currentPage -= 1
				render()
			})

			const pageLabel = document.createElement('span')
			pageLabel.className = 'shared-table-page-label'
			pageLabel.textContent = `Page ${currentPage} of ${totalPages}`

			const nextButton = document.createElement('button')
			nextButton.type = 'button'
			nextButton.className = 'shared-table-page-button'
			nextButton.textContent = 'Next'
			nextButton.disabled = currentPage >= totalPages
			nextButton.addEventListener('click', () => {
				if (currentPage >= totalPages) {
					return
				}
				currentPage += 1
				render()
			})

			pagination.append(previousButton, pageLabel, nextButton)
		}

		pageSizeSelect.addEventListener('change', () => {
			const selected = Number.parseInt(pageSizeSelect.value, 10)
			if (!Number.isFinite(selected) || selected <= 0) {
				return
			}
			pageSize = selected
			currentPage = 1
			render()
		})

		table.addEventListener('shared-table:sorted', () => {
			render()
		})

		render()
	})
}

const sharedTableBulkActions = () => {
	const bulkForms = Array.from(document.querySelectorAll('[data-bulk-actions]'))
	if (!bulkForms.length) {
		return
	}
	bulkForms.forEach((form) => {
		const targetSelector = form.dataset.bulkTarget
		const table = targetSelector ? document.querySelector(targetSelector) : form.querySelector('.shared-table')
		if (!table) {
			return
		}
		const submitButtons = Array.from(form.querySelectorAll('[data-bulk-submit]'))
		const checkboxes = () => Array.from(table.querySelectorAll('input[type="checkbox"]'))
		const updateState = () => {
			const selected = checkboxes().some((input) => input.checked)
			submitButtons.forEach((button) => {
				button.disabled = !selected
			})
		}
		updateState()
		table.addEventListener('change', (event) => {
			if (event.target && event.target.matches('input[type="checkbox"]')) {
				updateState()
			}
		})
		form.addEventListener('submit', (event) => {
			const selected = checkboxes().some((input) => input.checked)
			if (!selected) {
				event.preventDefault()
				return
			}
			const confirmMessage = form.dataset.bulkConfirm
			if (confirmMessage && !window.confirm(confirmMessage)) {
				event.preventDefault()
			}
		})
	})
}

document.addEventListener('DOMContentLoaded', () => {
	sharedTableSorting()
	sharedTablePagination()
	sharedTableBulkActions()
})
