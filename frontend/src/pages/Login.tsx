import SignInForm from '../components/SignInForm'

/** The sign-in page of the reporting institutions (/login). Bank staff have their own page, /staff/login. */
export default function Login() {
  return <SignInForm portal="external" />
}
