class BSCounter extends HTMLElement
{
    //form inclusion
    static formAssociated = true

    #internals = this.attachInternals()

    // shadow elements
    #counter
    #downBtn
    #upBtn

    constructor()
    {
        super()

        // counter options
        this.name = this.getAttribute('name')
        this.placeholder = this.getAttribute('placeholder') || this.#genPlaceholder()
        this.min = this.getAttribute('min')
        this.max = this.getAttribute('max')
        this.step = this.getAttribute('step')
        // default size to avoid min+max auto-resizing issues
        this.size = this.getAttribute('size') || 8
        
        // bs style options
        const btnStyle = this.getAttribute('btn-style') || 'btn-secondary'

        this.groupStyle = this.getAttribute('group-style') || ''
        this.controlStyle = this.getAttribute('control-style') || ''
        this.downStyle = this.getAttribute('down-style') || btnStyle
        this.upStyle = this.getAttribute('up-style') || btnStyle
        this.downIcon = this.getAttribute('down-icon') || 'bi-dash'
        this.upIcon = this.getAttribute('up-icon') || 'bi-plus'
    }
    
    connectedCallback()
    {
        this.attachShadow({ mode: 'open' })

        // template
        this.#importBS()
        this.#setupTemplate()
        
        // event binding
        this.addEventListener('keypress', e => {
            if (this.#internals.form && e.code === 'Enter') {
              this.#internals.form.submit()
            }
        })
        
        /** @author https://stackoverflow.com/a/74147301/30118204 */
        this.addEventListener('click', ({ target, x, y }) => {
            const relatedTarget = document.elementFromPoint(x, y)
            
            if(target === this && new Set(this.#internals.labels).has(relatedTarget))
                this.#counter.focus()
        })

        this.#downBtn.addEventListener('click', _ => {
            this.#counter.stepDown()
            this.#update()
        })
        this.#upBtn.addEventListener('click', _ => {
            this.#counter.stepUp()
            this.#update()
        })
        this.#counter.addEventListener('input', this.#update)

        // initial update
        this.#update()
    }
    
    get value() {
        return this.#counter.value
    }
    
    set value(value) {
        this.#counter.value = value
        
        this.#update()
    }

    // internal methods

    // returns a numerical attr as a number with the same precision as the step
    // option (ex: attr = "6", step = "0.05" -> 6.00) 
    #toPrecision = attr => {
        const stepDecimals = (this.step?.split('.').at(1)?.length || 0)
        const intLength = (String(attr).split('.').at(0).length || 0)
        
        return Number(attr || 0).toPrecision(intLength + stepDecimals)
    }

    // placeholder gives an indication of min/max values if any
    #genPlaceholder = () => {
        if (this.min && this.max)
            return [this.min, this.max].map(this.#toPrecision).join(' / ')
        else if (this.min) return this.#toPrecision(this.min) + ' / ?'
        else if (this.max) return '? / ' + this.#toPrecision(this.max)
        else return this.#toPrecision(0)
    }

    // grab a stylesheet with a data-bs-stylesheet attribute
    #getStyleSheet = name =>
        [...document.styleSheets].find(sheet => sheet.ownerNode.dataset.bsStylesheet === name)

    // add bs styles to the beginning of the shadow root
    #importBS = () =>
        this.shadowRoot.prepend(
            ...['bootstrap', 'bootstrap-icons'].map(id =>
                this.#getStyleSheet(id)?.ownerNode.cloneNode()
            )
        )
    
    #setupTemplate = () => {
        this.shadowRoot.innerHTML += `
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
        this.#counter = this.shadowRoot.querySelector('#counter')
        
        this.#counter.setAttribute('value', this.getAttribute('value'))
        
        if (this.min) this.#counter.setAttribute('min', this.min)
        if (this.max) this.#counter.setAttribute('max', this.max)
        if (this.step) this.#counter.setAttribute('step', this.step)
        
        this.#downBtn = this.shadowRoot.querySelector('#down')
        this.#upBtn = this.shadowRoot.querySelector('#up')
    }

    // dispatches update event after inner state update
    #update = () => {
        [this.#downBtn, this.#upBtn].forEach(btn => btn.classList.remove('disabled'))
        
        if (this.#counter.min && Number(this.#counter.value) <= Number(this.#counter.min))
            this.#downBtn.classList.add('disabled')
        if (
            this.#counter.value &&
            this.#counter.max &&
            Number(this.#counter.value) >= Number(this.#counter.max)
        )
            this.#upBtn.classList.add('disabled')

        this.#internals.setFormValue(this.#counter.value)

        this.dispatchEvent(new CustomEvent("bs-counter:update", {
            detail: this.#counter.value,
            bubbles: true,
            composed: true
        }))
    }
}

customElements.define('bs-counter', BSCounter)
