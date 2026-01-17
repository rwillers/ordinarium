(() => {
	const MOBILE_QUERY = "(max-width: 700px)";
	const media = window.matchMedia(MOBILE_QUERY);

	const getCarouselKey = (ul) => {
		const wrapper = ul.closest(".text-element");
		const heading = wrapper ? wrapper.querySelector("h3") : null;
		const title = heading ? heading.textContent.trim() : "";
		return title ? `text-carousel:${title}` : null;
	};

	const readStoredIndex = (ul) => {
		const key = getCarouselKey(ul);
		if (!key) {
			return null;
		}
		const stored = sessionStorage.getItem(key);
		if (!stored) {
			return null;
		}
		const parsed = Number.parseInt(stored, 10);
		return Number.isFinite(parsed) ? parsed : null;
	};

	const storeIndex = (ul, index) => {
		const key = getCarouselKey(ul);
		if (!key) {
			return;
		}
		sessionStorage.setItem(key, String(index));
	};

	const updateActiveDot = (ul, dots) => {
		const width = ul.clientWidth;
		if (!width) {
			return;
		}
		const index = Math.round(ul.scrollLeft / width);
		dots.forEach((dot, dotIndex) => {
			if (dotIndex === index) {
				dot.setAttribute("aria-current", "true");
			} else {
				dot.removeAttribute("aria-current");
			}
		});
		return index;
	};

	const setupCarousel = (ul) => {
		if (ul.dataset.carouselReady === "true") {
			return;
		}
		const items = Array.from(ul.children).filter(
			(child) => child.tagName === "LI"
		);
		if (items.length <= 1) {
			return;
		}

		ul.classList.add("text-carousel");
		ul.dataset.carouselReady = "true";

		const dotsWrap = document.createElement("div");
		dotsWrap.className = "text-carousel-dots";
		const dots = items.map((_, index) => {
			const dot = document.createElement("button");
			dot.type = "button";
			dot.className = "text-carousel-dot";
			dot.setAttribute("aria-label", `Show item ${index + 1}`);
			dot.addEventListener("click", () => {
				ul.scrollTo({
					left: ul.clientWidth * index,
					behavior: "smooth",
				});
				storeIndex(ul, index);
			});
			dotsWrap.appendChild(dot);
			return dot;
		});

		ul.insertAdjacentElement("afterend", dotsWrap);

		let ticking = false;
		let storeTimer = null;
		const onScroll = () => {
			if (ticking) {
				return;
			}
			ticking = true;
			requestAnimationFrame(() => {
				const index = updateActiveDot(ul, dots);
				ticking = false;
				if (index === undefined || index === null) {
					return;
				}
				if (storeTimer) {
					window.clearTimeout(storeTimer);
				}
				storeTimer = window.setTimeout(() => {
					storeIndex(ul, index);
				}, 180);
			});
		};
		ul.addEventListener("scroll", onScroll, { passive: true });
		window.addEventListener("resize", () => updateActiveDot(ul, dots));

		const storedIndex = readStoredIndex(ul);
		const initialIndex =
			storedIndex !== null
				? Math.max(0, Math.min(items.length - 1, storedIndex))
				: 0;
		requestAnimationFrame(() => {
			if (initialIndex > 0) {
				ul.scrollTo({ left: ul.clientWidth * initialIndex });
			}
			updateActiveDot(ul, dots);
		});
	};

	const init = () => {
		if (!media.matches) {
			return;
		}
		const root = document.querySelector("#text");
		if (!root) {
			return;
		}
		root
			.querySelectorAll(".text-element:not(.text-element-custom) ul")
			.forEach(setupCarousel);
	};

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}

	const onMediaChange = (event) => {
		if (event.matches) {
			init();
		}
	};

	if (typeof media.addEventListener === "function") {
		media.addEventListener("change", onMediaChange);
	} else if (typeof media.addListener === "function") {
		media.addListener(onMediaChange);
	}
})();
