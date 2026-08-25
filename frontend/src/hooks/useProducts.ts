import { useAsync } from './useAsync'
import { listProducts, getProduct, getProductInventory } from '../services/productApi'
import type { InventoryResponse, ProductResponse } from '../types/product'

/** Fetch the full storefront catalog. */
export function useProducts() {
  return useAsync<ProductResponse[]>(() => listProducts(), [])
}

/** Fetch a single product (and its stock level) by id. */
export function useProduct(productId: string | undefined) {
  const fetchProduct = (): Promise<ProductResponse> =>
    productId ? getProduct(productId) : Promise.reject(new Error('No product id given.'))
  const fetchInventory = (): Promise<InventoryResponse> =>
    productId ? getProductInventory(productId) : Promise.reject(new Error('No product id given.'))

  const product = useAsync<ProductResponse>(fetchProduct, [productId])
  const inventory = useAsync<InventoryResponse>(fetchInventory, [productId])
  return { product, inventory }
}
