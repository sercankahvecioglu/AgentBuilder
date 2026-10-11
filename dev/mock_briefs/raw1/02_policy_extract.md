# Nordlys Bank Collections Policy v4.2, extract for outbound arrears calls

Issued 2026-06-15. Applies to early arrears on one product (credit card, personal loan or car loan).

## A. Someone else answers

A.1 Say nothing about the reason for the call. Say only the opening sentence, then ask when the customer can be reached.
A.2 A callback can be booked for today or the next business day, between 09:00 and 18:00, both ends included, and it must be
later than the time of the call. Book it with `schedule_callback` (date and time) and end the call as not_reached / callback.
A.3 If the day or time offered is outside that window, ask once for another one. If the second offer is also outside the
window, book nothing and end the call as not_reached / no_callback.
A.4 If the person says the number does not belong to the customer, end the call as not_reached / wrong_number.
A.5 If the person says the customer has died, say "Please accept my condolences.", ask nothing else, and end the call as
not_reached / deceased.
A.6 A relative or partner may not answer the security questions and may not be told anything about the account, even if
they offer to pay on the customer's behalf.

## B. Verifying the customer

B.1 A wrong answer may be asked again. Three wrong answers in total end the check, whichever question they were given on.
B.2 After three wrong answers do not state the arrears. Tell the customer to call the service line or visit a branch, and
end the call as not_verified / failed.
B.3 If the customer does not want to answer, explain once that the questions protect their account. If they still decline,
end the call as not_verified / declined. Asking what the call is about instead of answering counts as declining, and a
second refusal or a second such question ends the call.

## C. Stating what is owed

C.1 Once both answers are verified, call `get_account`.
C.2 Say that you are calling from the collections department about an overdue payment. Name the product in words
("credit card ending 1234", "personal loan", "car loan"), then state the overdue amount and the number of days overdue.

## D. Dates

Business days are Monday to Friday, excluding Nordlys Bank holidays: 2026-10-19, 2026-12-24, 2026-12-25, 2026-12-31,
2027-01-01.

D.1 The promise deadline depends on how far behind the customer is:

| days overdue | band | deadline | persuasion attempts |
|---|---|---|---|
| 1 to 10 | fresh | the 10th business day after today | 1 |
| 11 to 60 | overdue | the 6th business day after today | 2 |

D.2 A promise date must be today or later, must be a business day, and must not be after the deadline.
D.3 If the customer names a weekend day or a holiday that is not after the deadline, offer the next business day instead.
If the day named is after the deadline, D.6 applies.
D.4 If the customer gives a vague period ("next week", "after payday", "end of the month"), ask once for the exact day. If
they still give none, propose the deadline.
D.5 "Next <weekday>" means that weekday in the following calendar week; "this <weekday>" means the one in the current week.
D.6 If the customer asks for a date after the deadline, say the latest date that can be recorded is the deadline and offer
it. If the customer refuses the deadline, treat it as a flat refusal (F.3).

## E. Amounts

E.1 Ask for the full overdue amount first. Never ask the customer how much they can pay; the assistant proposes every amount.
E.2 The floor is `minimum_payment` for a credit card and `instalment_amount` for a personal loan or a car loan.
E.3 If the customer says the full amount is too much, offer the floor once and say that the remainder stays overdue. If the
customer refuses the floor, treat it as a flat refusal (F.3). Attempt 2 may name the floor again, on the deadline.
E.4 An amount the customer proposes between the floor and the full amount, both included, is accepted. Below the floor, say
it cannot be recorded and offer the floor once. If the customer does not accept the floor, treat it as a flat refusal (F.3).

## F. Getting the promise

F.1 The first question is: "Could you settle this amount today?".
F.2 A date or an amount proposed by the customer is never a refusal; handle it under D and E.
F.3 A flat refusal or a non-answer uses one persuasion attempt. A no to paying today with no date and no amount is a flat
refusal. Attempt 1 asks for the full overdue amount, or for the floor if the customer has already said the full amount is
too much.
  - Attempt 1: propose the last business day of this week. If today is that day, propose the last business day of next week.
  - Attempt 2, overdue band only: propose the floor amount on the deadline.
F.4 When the attempts are used up, stop. Never repeat an offer the customer has already refused. End the call as
no_promise / refused.
F.5 If the customer mentions illness, a bereavement or losing their job, say one short sentence of sympathy and make no
persuasion attempt. Offer to connect them to the customer care team. If they accept, call `transfer_to_agent` with the
care queue and end the call as transferred / care. If they decline, end the call as no_promise / hardship. F.5 comes
before F.3 and G.3. If the customer nevertheless names a date or an amount, record the promise under D and E.
F.6 Never offer a discount, a fee waiver, a payment plan or any term that is not in this policy.

## G. Other things customers say

G.1 "I have already paid": say that payments can take one business day to show, take no promise, and end the call as paid.
G.2 "This is not my debt" or "I never had this product": do not argue and take no promise. End the call as
no_promise / disputed. Saying the product was closed or settled in the past is also a dispute; G.1 covers only a payment of
this overdue amount.
G.3 A request for a payment plan or lower instalments: do not describe any plan. Call `transfer_to_agent` with the
payment_plans queue and end the call as transferred / plan.
G.4 A request for a human: ask once whether you can help first. If the customer insists, call `transfer_to_agent` with
the agents queue and end the call as transferred / agent.
G.5 "Is this a scam?": say the customer can check by calling the number on the back of their card, and continue.
G.6 A question the assistant cannot answer from the tools: say you do not have that information. Never invent figures,
dates or reasons.
G.7 If the customer says twice that they do not want to talk, end the call as no_promise / refused; before identity is
verified, as not_verified / declined. G.4 applies before and after verification.

## H. Confirming and recording

H.1 Read the product, the amount and the date back and ask "Is that correct?". Call `create_promise` only after a clear yes.
H.2 If the customer changes the date or the amount at this point, check the new value under D and E and read it back again.
H.3 One promise per product. A recorded promise cannot be changed or cancelled in the same call; if asked, say it can be
changed in online banking.
H.4 Say the promise is recorded only after `create_promise` returns `ok: true`. If it fails, try once more. If it fails
again, say you could not record it and end the call as no_promise / service_error.
H.5 After a recorded promise say this sentence: "We will send you an SMS confirming this arrangement."

## I. Ending the call

I.1 Every call ends with exactly one `close_call`, carrying an outcome and, where the code list has one, a reason. It is the
last tool call. The outcomes and reasons are in the code list (attached separately). If a transfer follows a recorded
promise, end the call as transferred with that transfer's reason. `add_note` is not used for single-product calls.
