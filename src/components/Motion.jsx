/**
 * Motion.jsx — shared Framer Motion wrappers for micro-interactions.
 *
 * Exports:
 *   MotionButton  — scale on hover + tap, replaces <button> for primary CTAs
 *   MotionCard    — lift + glow on hover, replaces outermost <div> for cards
 *   PageShell     — fade-up entrance/exit wrapper for full-page components
 *   StaggerList   — container that staggers children entrance animations
 *   StaggerItem   — individual item inside a StaggerList
 */
import { motion } from 'framer-motion'

export const MotionButton = ({ children, style, className, onClick, disabled, type, ...rest }) => (
  <motion.button
    whileHover={disabled ? {} : { scale: 1.03 }}
    whileTap={disabled ? {} : { scale: 0.96 }}
    transition={{ type: 'spring', stiffness: 400, damping: 20 }}
    style={style}
    className={className}
    onClick={onClick}
    disabled={disabled}
    type={type}
    {...rest}
  >
    {children}
  </motion.button>
)

export const MotionCard = ({ children, style, className, onClick, ...rest }) => (
  <motion.div
    whileHover={{
      y: -3,
      boxShadow: '0 12px 40px rgba(59,130,246,0.18)',
    }}
    transition={{ duration: 0.2, ease: 'easeOut' }}
    style={style}
    className={className}
    onClick={onClick}
    {...rest}
  >
    {children}
  </motion.div>
)

export const PageShell = ({ children, style, ...rest }) => (
  <motion.div
    initial={{ opacity: 0, y: 16 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -8 }}
    transition={{ duration: 0.22, ease: 'easeOut' }}
    style={{ minHeight: '100vh', ...style }}
    {...rest}
  >
    {children}
  </motion.div>
)

const listVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06 } },
}
const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.22, ease: 'easeOut' } },
}

export const StaggerList = ({ children, style, className, ...rest }) => (
  <motion.div
    variants={listVariants}
    initial="hidden"
    animate="show"
    style={style}
    className={className}
    {...rest}
  >
    {children}
  </motion.div>
)

export const StaggerItem = ({ children, style, className, ...rest }) => (
  <motion.div variants={itemVariants} style={style} className={className} {...rest}>
    {children}
  </motion.div>
)
