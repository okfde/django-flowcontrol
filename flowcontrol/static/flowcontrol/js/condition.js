const TT = {
  NUMBER: 'number',
  STRING: 'string',
  NAME:   'NAME',
  INFIX:  'INFIX',
  PREFIX: 'PREFIX',
  PIPE:   'PIPE',
  COLON:  'COLON',
};

const INFIX_OPS  = ['not in','is not','>=','<=','==','!=','>','<','in','is','and','or'];
const PREFIX_OPS = ['not'];

function tokenize(src) {
  const tokens = [];
  let i = 0;
  const s = src.trim();

  while (i < s.length) {
    if (/\s/.test(s[i])) { i++; continue; }

    if (s[i] === '|') { tokens.push({ type: TT.PIPE,  value: '|' }); i++; continue; }
    if (s[i] === ':') { tokens.push({ type: TT.COLON, value: ':' }); i++; continue; }

    if (s[i] === '"' || s[i] === "'") {
      const q = s[i++];
      let str = '';
      while (i < s.length && s[i] !== q) { if (s[i] === '\\') i++; str += s[i++]; }
      if (s[i] !== q) throw new Error(`Unterminated string at position ${i}`);
      i++;
      tokens.push({ type: TT.STRING, value: str, raw: q + str + q });
      continue;
    }

    if (/[0-9]/.test(s[i]) || (s[i] === '-' && /[0-9]/.test(s[i+1] || ''))) {
      let num = '';
      if (s[i] === '-') num += s[i++];
      while (i < s.length && /[0-9.]/.test(s[i])) num += s[i++];
      tokens.push({ type: TT.NUMBER, value: parseFloat(num), raw: num });
      continue;
    }

    if (/[a-zA-Z_]/.test(s[i])) {
      let word = '';
      while (i < s.length && /[a-zA-Z0-9_.:@-]/.test(s[i]) && s[i] !== '|' && s[i] !== ':') word += s[i++];

      // try two-word operator: peek past whitespace for a second keyword
      const rest = s.slice(i);
      const secondMatch = rest.match(/^\s+([a-zA-Z_]+)/);
      if (secondMatch) {
        const tryTwo = word + ' ' + secondMatch[1];
        if (INFIX_OPS.includes(tryTwo)) {
          i += secondMatch[0].length;
          tokens.push({ type: TT.INFIX, value: tryTwo });
          continue;
        }
      }

      if (PREFIX_OPS.includes(word)) { tokens.push({ type: TT.PREFIX, value: word }); continue; }
      if (INFIX_OPS.includes(word))  { tokens.push({ type: TT.INFIX,  value: word }); continue; }
      tokens.push({ type: TT.NAME, value: word });
      continue;
    }

    if (/[><!=]/.test(s[i])) {
      const two = s.slice(i, i+2);
      if (['>=','<=','==','!='].includes(two)) { tokens.push({ type: TT.INFIX, value: two }); i+=2; continue; }
      if (s[i] === '>' || s[i] === '<')        { tokens.push({ type: TT.INFIX, value: s[i] }); i++;  continue; }
    }

    throw new Error(`Unexpected character '${s[i]}' at position ${i}`);
  }
  return tokens;
}

function parseExpression(src) {
  let tokens;
  try {
    tokens = tokenize(src);
    console.log(tokens)
  } catch(e) {
    return null
  }

  if (!tokens.length) { 
    return null
  }

  const comparisons = []
  const operators = []
  const makeComparison = () => ({
    current: "operand1",
    operand1Filters: null,
    operand1: null,
    operator: "true",
    operand2: null,
    operand2Filters: null,
  })
  let i = 0
  let comparison = makeComparison()
  while (i < tokens.length) {
    let token = tokens[i]
    if (token.type === "PREFIX" && token.value === "not") {
      comparison.operator = "false"
    } else if (token.type === "INFIX" && ["and", "or"].includes(token.value)) {
      comparisons.push(comparison)
      operators.push(token.value)
      comparison = makeComparison()
    } else if (token.type === "INFIX") {
      comparison.operator = token.value
      comparison.current = "operand2"
    } else if (token.type === "NAME") {
      if (token.value.startsWith("object")) {
        const value = token.value.replace(/object\.?/, "")
        comparison[comparison.current] = {
          type: "object", value
        }
      } else {
        comparison[comparison.current] = {
          type: "state", value: token.value
        }
      }
    } else if (token.type === "PIPE") {
      comparison[comparison.current + "Filters"] = comparison[comparison.current + "Filters"] || []
      i += 1
      token = tokens[i]
      comparison[comparison.current + "Filters"].push(
        {name: token.value, argument: null}
      )
    } else if (token.type === "COLON") {
      const filtLength = comparison[comparison.current + "Filters"].length
      const lastFilt = comparison[comparison.current + "Filters"][filtLength - 1]
      i += 1
      token = tokens[i]
      lastFilt.argument = token
    } else {
      comparison[comparison.current] = token
    }
    i += 1;
  }

  comparisons.push(comparison)

  return {
    comparisons,
    operators
  }
}


const removeEvent = new CustomEvent("remove", {
  bubbles: false,
  cancelable: false,
  composed: true
});

const changeEvent = new CustomEvent("changecondition", {
  bubbles: true,
  cancelable: false,
  composed: true
});

const dispatchChange = function () {
  this.dispatchEvent(changeEvent)
}

const conditionCSS = new CSSStyleSheet()

conditionCSS.replaceSync(`
  :host > div > select {
    margin-bottom: 2em;
  }
`)

class FlowcontrolCondition extends HTMLElement {
  #shadow;
  static define() {
    customElements.define("flowcontrol-condition", this)
    FlowcontrolComparison.define();
    FlowcontrolComparisonOperand.define();
  }
  constructor() {
    super();
    this.#shadow = this.attachShadow({ mode: 'open' });
    this.#shadow.adoptedStyleSheets = [conditionCSS]
  }
  connectedCallback() {
    this.srcInput = this.parentElement.querySelector("textarea")
    this.config = JSON.parse(this.getAttribute('config') || '{}');
    this.comparisonContainer = document.createElement("div")
    this.#shadow.appendChild(this.comparisonContainer)
    this.#shadow.addEventListener("changecondition", this.updateInput.bind(this))

    const addMoreButton = document.createElement("button")
    addMoreButton.textContent = "+"
    addMoreButton.addEventListener("click", () => {
      this.addComparison()
      this.updateInput()
    })
    this.#shadow.appendChild(addMoreButton)
    this.initFromSrc()
  }
  initFromSrc() {
    const src = this.srcInput.value;
    const parsed = parseExpression(src);
    if (parsed === null) {
      return
    }
    parsed.comparisons.forEach((comp, i) => {
      const result = this.addComparison()
      result.comparison.setParsed(comp)
      if (result.operator) {
        result.operator.value = parsed.operators[i - 1]
      }
    })
  }
  updateInput() {
    this.srcInput.value = this.value
  }

  addComparison () {
    const comparison = document.createElement('flowcontrol-comparison');
    comparison.addEventListener("remove", (e) => {
      if (e.target.nextSibling) {
        e.target.nextSibling.remove()
      }
      e.target.remove()
      this.updateInput()
    })
    comparison.setConfig(this.config);
    let operator = null
    if (this.#shadow.querySelectorAll("flowcontrol-comparison").length > 0) {
      operator = this.addOperator()
    }
    this.comparisonContainer.appendChild(comparison)
    return {
      comparison,
      operator
    }
  }
  addOperator () {
    const operator = document.createElement("select")
    operator.addEventListener("change", this.updateInput.bind(this))
    this.config.operators.forEach(opt => {
      const option = document.createElement('option');
      option.value = opt.value;
      option.textContent = opt.label;
      operator.appendChild(option);
    })
    this.comparisonContainer.appendChild(operator)
    return operator
  }

  get value() {
    const comps = this.comparisonContainer.querySelectorAll("flowcontrol-comparison")
    const ops = this.comparisonContainer.querySelectorAll("select")
    let result = []
    for (let i = 0; i < comps.length; i += 1) {
      result.push(comps[i].value)
      if (i + 1 < comps.length) {
        result.push(ops[i].value)
      }
    }
    return result.join(" ")
  }
}


const comparisonCSS = new CSSStyleSheet()

comparisonCSS.replaceSync(`
  :host {
    display: flex;
    margin-bottom: 2em;
  }
  :host > * {
    flex: 1 auto;
  }
  :host >*:nth-child(1) {
    width: 35%;
  }
  :host >*:nth-child(2) {
    width: 20%;
  }
  :host >*:nth-child(3) {
    width: 35%;
  }
  :host >*:last-child {
    margin-end: auto;
    width: 5%;
    max-height: 2rem;
  }
`)


class FlowcontrolComparison extends HTMLElement {
  #shadow;
  static define() {
    customElements.define("flowcontrol-comparison", this)
  }
  constructor() {
    super();
    this.#shadow = this.attachShadow({ mode: 'open' })
    this.#shadow.adoptedStyleSheets = [comparisonCSS]
  }
  connectedCallback() {
    this.operand1 = document.createElement('flowcontrol-comparisonoperand');
    this.operator = document.createElement('select');
    this.operator.addEventListener("change", dispatchChange.bind(this))
    this.config.comparisons.forEach(opt => {
      const option = document.createElement('option');
      option.value = opt.value;
      option.textContent = opt.label;
      this.operator.appendChild(option);
    });

    this.operand2 = document.createElement('flowcontrol-comparisonoperand');
    this.operand2.hidden = true;

    this.operand1.setConfig(this.config);
    this.operand2.setConfig(this.config);

    this.operator.addEventListener("change", (e) => {
      this.operatorChanged()
      dispatchChange.bind(this)()
    })

    this.#shadow.appendChild(this.operand1);
    const operatorContainer = document.createElement("div")
    operatorContainer.appendChild(this.operator)
    this.#shadow.appendChild(operatorContainer);
    this.#shadow.appendChild(this.operand2);

    const removeButton = document.createElement("button")
    removeButton.textContent = "-"
    removeButton.addEventListener("click", (e) => {
      this.dispatchEvent(removeEvent)
    })
    this.#shadow.appendChild(removeButton)
  }
  operatorChanged() {
    if (["true", "false"].includes(this.operator.value)) {
      this.operand2.hidden = true
    } else {
      this.operand2.hidden = false
    }
  }
  setConfig(config) {
    this.config = config;
  }
  setParsed(comparison) {
    this.operand1.setParsed(comparison.operand1, comparison.operand1Filters)
    this.operator.value = comparison.operator
    this.operatorChanged()
    if (comparison.operand2) {
      this.operand2.setParsed(comparison.operand2, comparison.operand2Filters)
    }
  }
  get value() {
    const op = this.operator.value;

    const result = []
    if (op === "false") {
      result.push("not")
    }
    result.push(this.operand1.value)
    if (!["true", "false"].includes(op)) {
      result.push(op)
      result.push(this.operand2.value)
    }
    return result.join(" ")
  }
}


class FlowcontrolComparisonOperand extends HTMLElement {
  #shadow;
  static define() {
    customElements.define("flowcontrol-comparisonoperand", this)
    FlowcontrolFilter.define()
  }
  constructor() {
    super();
    this.#shadow = this.attachShadow({ mode: 'open' })
    this.filters = []
  }
  connectedCallback() {
    this.types = {}

    this.state_path = document.createElement('input');
    this.state_path.addEventListener("change", dispatchChange.bind(this))
    this.state_path.type = 'text';
    this.state_path.hidden = true;
    this.types["state"] = this.state_path

    this.object_attr = document.createElement('select');
    this.object_attr.addEventListener("change", dispatchChange.bind(this))
    this.object_attr.hidden = true; 
    this.config.object_attributes.forEach(opt => {
      const option = document.createElement('option');
      option.value = opt.value;
      option.textContent = opt.label;
      this.object_attr.appendChild(option);
    })
    this.types["object"] = this.object_attr

    this.string_input = document.createElement('input')
    this.string_input.addEventListener("change", dispatchChange.bind(this))
    this.string_input.type = "text"
    this.string_input.hidden = true
    this.types["string"] = this.string_input

    this.number_input = document.createElement('input')
    this.number_input.addEventListener("change", dispatchChange.bind(this))
    this.number_input.type = "number"
    this.number_input.hidden = true
    this.types["number"] = this.number_input

    this.type = document.createElement('select');
    this.config.operand_types.forEach(opt => {
      const option = document.createElement('option');
      option.value = opt.value;
      option.textContent = opt.label;
      this.type.appendChild(option);
    });
    
    this.type.addEventListener('change', this.typeChanged.bind(this))
    this.type.addEventListener("change", dispatchChange.bind(this))

    this.#shadow.appendChild(this.type);

    for (const key in this.types) {
      this.#shadow.appendChild(this.types[key]);
    }

    this.filterContainer = null
    if (this.hasFilters) {
      this.filterContainer = document.createElement("div")
      this.addFilterButton = document.createElement("button")
      this.addFilterButton.textContent = "+F"
      this.addFilterButton.addEventListener("click", () => {
        this.addFilter()
        dispatchChange.bind(this)()
      })
      this.filterContainer.appendChild(this.addFilterButton)
      this.#shadow.appendChild(this.filterContainer)
    }

    this.typeChanged()
  }
  setConfig(config, hasFilters = true, onlyType = null) {
    this.config = config;
    this.hasFilters = hasFilters
    this.onlyType = onlyType

    window.setTimeout(() => {
      this.type.querySelectorAll("option").forEach(opt => {
        opt.disabled = this.onlyType && ["string", "number"].includes(opt.value) && this.onlyType != opt.value
      })
    }, 10)
  }
  setParsed(operand, filters) {
    this.type.value = operand.type
    this.types[this.type.value].value = operand.value
    this.typeChanged()
    if (filters) {
      filters.forEach(filt => {
        const filter = this.addFilter()
        filter.setParsed(filt)
      })
    }
  }
  typeChanged() {
    for (const key in this.types) {
      this.types[key].hidden = true
    }
    this.types[this.type.value].hidden = false
  }
  addFilter() {
    const filt = document.createElement("flowcontrol-filter")
    filt.setConfig(this.config)
    this.filterContainer.insertBefore(filt, this.addFilterButton)
    return filt
  }
  get value() {
    const result = []
    if (this.type.value === "object") {
      if (this.object_attr.value === "") {
        result.push("object")
      } else {
        result.push("object." + this.object_attr.value)
      }
    } else if (this.type.value === "state") {
      result.push(this.state_path.value)
    } else if (this.type.value == "string") {
      result.push('"' + this.string_input.value.replace(/"/g, '\\"') + '"')
    } else if (this.type.value == "number") {
      result.push(this.number_input.value)
    }
    if (this.filterContainer) {
      const filters = this.filterContainer.querySelectorAll("flowcontrol-filter")
      filters.forEach(f => result.push(f.value))
    }
    return result.join("")
  }
}


class FlowcontrolFilter extends HTMLElement {
  #shadow;
  static define() {
    customElements.define("flowcontrol-filter", this)
  }
  constructor() {
    super();
    this.#shadow = this.attachShadow({ mode: 'open' })
  }
  connectedCallback() {
    this.filter = document.createElement('select');
    this.filter.addEventListener("change", () => {
      this.filterChanged()
      dispatchChange.bind(this)()
    })
    this.config.filters.forEach(opt => {
      const option = document.createElement('option');
      option.value = opt.name;
      option.textContent = opt.name;
      this.filter.appendChild(option);
    });
    this.#shadow.appendChild(this.filter);

    this.filterArgument = document.createElement("flowcontrol-comparisonoperand")
    this.filterArgument.setConfig(this.config, false)
    this.filterArgument.hidden = true
    this.#shadow.appendChild(this.filterArgument)
    this.filterChanged()
    const removeButton = document.createElement("button")
    removeButton.textContent = "-"
    removeButton.addEventListener("click", (e) => {
      this.remove()
      dispatchChange.bind(this)()
    })
    this.#shadow.appendChild(removeButton)
  }
  filterChanged () {
    const filtConfig = this.config.filters.find((f) => f.name === this.filter.value)
    if (filtConfig.argument) {
      this.filterArgument.hidden = false
    } else {
      this.filterArgument.hidden = false
    }
    this.filterArgument.setConfig(this.config, false, filtConfig.argument)
  }
  setConfig(config) {
    this.config = config;
  }
  setParsed(filt) {
    console.log("parsed filter", filt)
    this.filter.value = filt.name
    if (filt.argument) {
      this.filterArgument.setParsed(filt.argument)
    }
    this.filterChanged()
  }
  get value() {
    const parts = ["|" + this.filter.value]
    if (!this.filterArgument.hidden) {
      const val = this.filterArgument.value
      if (val) {
        parts.push(val)
      }
    }
    return parts.join(":")
  }
}

FlowcontrolCondition.define();
