export const UNIVERSITY_EMAIL_MESSAGE = 'Use your @charlotte.edu or @uncc.edu email.'

export function isUniversityEmail(value: string): boolean {
  return /^[^\s@]+@(?:charlotte|uncc)\.edu$/i.test(value.trim())
}
