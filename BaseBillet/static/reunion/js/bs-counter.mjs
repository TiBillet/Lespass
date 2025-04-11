class BSCounter extends HTMLElement
{
    static formAssociated = true
    #counter
    #downBtn
    #upBtn

    constructor()
    {
        super()

        this.internals_ = this.attachInternals()
        
        this.min = this.getAttribute('min')
        this.max = this.getAttribute('max')
        this.step = this.getAttribute('step')
        this.name = this.getAttribute('name')
        this.size = this.getAttribute('size') || 8
        
        const btnStyle = this.getAttribute('btn-style') || 'btn-secondary'

        this.groupStyle = this.getAttribute('group-style') || ''
        this.controlStyle = this.getAttribute('control-style') || ''
        this.downStyle = this.getAttribute('down-style') || btnStyle
        this.upStyle = this.getAttribute('up-style') || btnStyle
        this.downIcon = this.getAttribute('down-icon') || 'bi-dash'
        this.upIcon = this.getAttribute('up-icon') || 'bi-plus'

        const toPrecision = n => {
            const stepDecimals = (this.getAttribute('step')?.split('.').at(1)?.length || 0)
            const intLength = (String(n).split('.').at(0).length || 0)
            
            return Number(n || 0).toPrecision(intLength + stepDecimals)
        }

        const genPlaceholder = () => {
            if (this.min && this.max)
                return [this.min, this.max].map(toPrecision).join(' / ')
            else if (this.min) return toPrecision(this.min) + ' / ?'
            else if (this.max) return '? / ' + toPrecision(this.max)
            else return toPrecision(0)
        }

        this.placeholder = genPlaceholder()
    }
    
    connectedCallback()
    {
        const root = this.attachShadow({ mode: 'open' })

        const getStyleSheet = (id) =>
            [...document.styleSheets].find(sheet => sheet.ownerNode.dataset.bsStylesheet === id)
        
        root.prepend(...['bootstrap', 'bootstrap-icons'].map(id => getStyleSheet(id)?.ownerNode.cloneNode()))
        
        root.innerHTML += `
            <style>
                /* Chrome, Safari, Edge, Opera */
                input::-webkit-outer-spin-button,
                input::-webkit-inner-spin-button {
                    -webkit-appearance: none;
                    margin: 0;
                }
                /* Firefox */
                input[type=number] {
                    -moz-appearance: textfield;
                }
                .input-group > .form-control {    
                    width: ${Number(this.size) + 1}rem;
                }
                .form-control::placeholder {
                    opacity: 0.5;
                }
            </style>
            <div class="input-group flex-nowrap ${this.groupStyle}">
                <button id="down" class="btn ${this.downStyle}" type="button">
                    <slot name="down-label">
                        <i class="bi ${this.downIcon}"></i>
                    </slot>
                </button>
                <input
                    id="counter"
                    name="${this.name}"
                    class="form-control text-end ${this.controlStyle}"
                    type="number"
                    size="${this.size}"
                    placeholder="${this.placeholder}"
                    aria-label="Number counter with pretty buttons"
                />
                <button id="up" class="btn ${this.upStyle}" type="button">
                    <slot name="up-label">
                        <i class="bi ${this.upIcon}"></i>
                    </slot>
                </button>
            </div>
        `
        this.#counter = root.querySelector('#counter')

        if (this.min) this.#counter.setAttribute('min', this.min)
        if (this.max) this.#counter.setAttribute('max', this.max)
        if (this.step) this.#counter.setAttribute('step', this.step)
        
        this.#counter.setAttribute('value', this.getAttribute('value'))
        
        this.#downBtn = root.querySelector('#down')
        this.#upBtn = root.querySelector('#up')

        
        this.addEventListener('keypress', e => {
            if (this.internals_.form && e.code === 'Enter') {
              this.internals_.form.submit()
            }
        })
        
        /** @author https://stackoverflow.com/a/74147301/30118204 */
        this.addEventListener('click', ({ target, x, y }) => {
            const relatedTarget = document.elementFromPoint(x, y)
            
            if(target === this && new Set(this.internals_.labels).has(relatedTarget))
                this.#counter.focus()
        })

        this.#downBtn.addEventListener('click', _ => {
            this.#counter.stepDown()
            this.update()
        })
        this.#upBtn.addEventListener('click', _ => {
            this.#counter.stepUp()
            this.update()
        })
        this.#counter.addEventListener('input', this.update.bind(this))

        this.update()
    }
    
    get value() {
        return this.#counter.value
    }
    
    set value(value) {
        if (value) {
            this.#counter.value = value
            
            this.update()
        }
    }

    update() {
        [this.#downBtn, this.#upBtn].forEach(btn => btn.classList.remove('disabled'))
        
        if (this.#counter.min && Number(this.#counter.value) <= Number(this.#counter.min))
            this.#downBtn.classList.add('disabled')
        if (
            this.#counter.value &&
            this.#counter.max &&
            Number(this.#counter.value) >= Number(this.#counter.max)
        )
            this.#upBtn.classList.add('disabled')

        this.internals_.setFormValue(this.#counter.value)

        this.dispatchEvent(new CustomEvent("bs-counter:update", {
            detail: this.#counter.value,
            bubbles: true,
            composed: true
        }))
    }
}

customElements.define('bs-counter', BSCounter)
