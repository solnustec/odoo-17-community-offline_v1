/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

/**
 * LazyImage Component
 *
 * OWL component that implements lazy loading of images using IntersectionObserver.
 * Images are only loaded when they become visible in the viewport.
 *
 * Features:
 * - IntersectionObserver for visibility detection
 * - Placeholder display while loading
 * - Fallback to initials avatar if no image
 * - Fade-in animation on load
 * - Automatic cleanup on unmount
 */
export class LazyImage extends Component {
    static template = "hr_kanban_optimization.LazyImage";
    static props = {
        employeeId: { type: Number },
        employeeName: { type: String, optional: true },
        hasImage: { type: Boolean, optional: true },
        size: { type: String, optional: true },
        cssClass: { type: String, optional: true },
        placeholder: { type: String, optional: true },
    };
    static defaultProps = {
        employeeName: "",
        hasImage: false,
        size: "128",
        cssClass: "",
        placeholder: "",
    };

    setup() {
        this.rpc = useService("rpc");
        this.imageRef = useRef("imageContainer");
        this.observer = null;

        this.state = useState({
            isLoading: false,
            isLoaded: false,
            isVisible: false,
            imageData: null,
            error: false,
        });

        // Image cache - shared across instances
        if (!LazyImage.imageCache) {
            LazyImage.imageCache = new Map();
        }

        onMounted(() => {
            this.setupIntersectionObserver();
        });

        onWillUnmount(() => {
            this.cleanupObserver();
        });
    }

    /**
     * Setup IntersectionObserver to detect when image enters viewport
     */
    setupIntersectionObserver() {
        if (!this.imageRef.el) return;

        const options = {
            root: null, // viewport
            rootMargin: "100px", // Start loading 100px before visible
            threshold: 0.1, // Trigger when 10% visible
        };

        this.observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting && !this.state.isLoaded && !this.state.isLoading) {
                    this.state.isVisible = true;
                    this.loadImage();
                }
            });
        }, options);

        this.observer.observe(this.imageRef.el);
    }

    /**
     * Cleanup observer on component unmount
     */
    cleanupObserver() {
        if (this.observer) {
            this.observer.disconnect();
            this.observer = null;
        }
    }

    /**
     * Load image data from server
     */
    async loadImage() {
        if (!this.props.hasImage) {
            this.state.isLoaded = true;
            return;
        }

        const cacheKey = `${this.props.employeeId}_${this.props.size}`;

        // Check cache first
        if (LazyImage.imageCache.has(cacheKey)) {
            this.state.imageData = LazyImage.imageCache.get(cacheKey);
            this.state.isLoaded = true;
            return;
        }

        this.state.isLoading = true;
        this.state.error = false;

        try {
            const result = await this.rpc("/web/dataset/call_kw/hr.employee/get_employee_image", {
                model: "hr.employee",
                method: "get_employee_image",
                args: [this.props.employeeId, this.props.size],
                kwargs: {},
            });

            if (result.success && result.has_image && result.image_data) {
                this.state.imageData = result.image_data;
                // Cache the image data
                LazyImage.imageCache.set(cacheKey, result.image_data);
            } else {
                this.state.imageData = null;
            }
            this.state.isLoaded = true;
        } catch (error) {
            console.error("LazyImage: Error loading image for employee", this.props.employeeId, error);
            this.state.error = true;
            this.state.isLoaded = true;
        } finally {
            this.state.isLoading = false;
        }
    }

    /**
     * Get initials from employee name for placeholder
     */
    get initials() {
        if (!this.props.employeeName) return "?";
        const parts = this.props.employeeName.trim().split(" ");
        if (parts.length >= 2) {
            return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
        }
        return parts[0].substring(0, 2).toUpperCase();
    }

    /**
     * Generate background color based on employee ID (consistent color)
     */
    get placeholderColor() {
        const colors = [
            "#F06050", "#F4A460", "#F7CD1F", "#6CC1ED", "#814968",
            "#EB7E7F", "#2C8397", "#475577", "#D6145F", "#30C381"
        ];
        return colors[this.props.employeeId % colors.length];
    }

    /**
     * Get image source with proper prefix
     */
    get imageSrc() {
        if (!this.state.imageData) return null;
        // Check if already has data URI prefix
        if (this.state.imageData.startsWith("data:")) {
            return this.state.imageData;
        }
        return `data:image/png;base64,${this.state.imageData}`;
    }

    /**
     * CSS classes for the image container
     */
    get containerClasses() {
        const classes = ["o_lazy_image_container", this.props.cssClass];
        if (this.state.isLoading) classes.push("o_lazy_image_loading");
        if (this.state.isLoaded) classes.push("o_lazy_image_loaded");
        if (this.state.error) classes.push("o_lazy_image_error");
        return classes.filter(Boolean).join(" ");
    }
}

// Register the component for use in templates
registry.category("components").add("LazyImage", LazyImage);
