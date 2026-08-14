import { priceTag, qualityLabel, sizeTooltip } from '../format'
import { isSoldOut } from '../products'
import type { MediaKind, Product, ProductOption } from '../types'

interface Props {
  heading: string
  products: Product[]
  selected: ProductOption | null
  onSelect: (kind: MediaKind, option: ProductOption) => void
}

/** 진열대 한 층. 윗칸은 음원(캔), 아랫칸은 영상(병). */
export default function Shelf({ heading, products, selected, onSelect }: Props) {
  if (products.length === 0) return null

  return (
    <section className="shelf" aria-label={`${heading} 진열대`}>
      <h3 className="shelf__heading">{heading}</h3>
      <div className="shelf__rail">
        {products.map((product) => (
          <ProductSlot
            key={product.format}
            product={product}
            selected={selected}
            onSelect={(option) => onSelect(product.kind, option)}
          />
        ))}
      </div>
    </section>
  )
}

function ProductSlot({
  product,
  selected,
  onSelect,
}: {
  product: Product
  selected: ProductOption | null
  onSelect: (option: ProductOption) => void
}) {
  const soldOut = isSoldOut(product)
  const vessel = product.kind === 'audio' ? 'can' : 'bottle'

  return (
    <div
      className={`product${soldOut ? ' product--soldout' : ''}`}
      data-testid={`product-${product.format}`}
    >
      {soldOut && (
        <span className="soldout-tag" aria-hidden="true">
          SOLD OUT
        </span>
      )}
      <div className="product__head">
        <span className={`vessel vessel--${vessel}`} aria-hidden="true">
          <span className="vessel__label">{product.title}</span>
        </span>
        <h4 className="product__name">
          {product.title}
          <span className="product__hint">{product.kind === 'audio' ? '음원' : '영상'}</span>
        </h4>
      </div>

      <ul className="dials">
        {product.options.map((option) => (
          <li key={option.quality}>
            <button
              type="button"
              className="dial"
              data-testid={`option-${option.format}-${option.quality}`}
              onClick={() => onSelect(option)}
              disabled={!option.available}
              aria-pressed={selected === option}
              aria-label={ariaLabel(option)}
              title={option.available ? sizeTooltip(option.sizeSource) : (option.note ?? '품절')}
            >
              <span className="dial__quality">
                {qualityLabel(option.format, option.quality)}
                {option.badge && <span className="badge">{option.badge}</span>}
              </span>
              <span className="dial__price">{option.available ? priceTag(option) : 'SOLD OUT'}</span>
            </button>
            {option.note && !option.available && <p className="dial__note">{option.note}</p>}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ariaLabel(option: ProductOption): string {
  const quality = qualityLabel(option.format, option.quality)
  const name = option.format.toUpperCase()
  if (!option.available) {
    return `${name} ${quality}, 품절${option.note ? `, ${option.note}` : ''}`
  }
  const badge = option.badge ? `, ${option.badge}` : ''
  return `${name} ${quality}, 예상 용량 ${priceTag(option)}${badge}`
}
