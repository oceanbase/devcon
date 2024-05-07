import 'bulma/css/bulma.css'
import './dark.css'
import { Form, Checkbox, Radio, Space, Typography, Button, Input } from 'antd'
import React from 'react'
import questionsData from './questions.json'

enum QuestionType {
  MultipleChoice = 'MultipleChoice',
  SingleChoice = 'SingleChoice',
}

type QuestionAnswer = {
  content: string
  isCorrect?: boolean
}

type Question = {
  id: string
  title: string
  description?: string
  type: string
  answers: QuestionAnswer[]
}

const questions: Question[] = questionsData.questionsData

const correctMapping: Record<string, string[]> = Object.fromEntries(questions.map((q) => [q.id, q.answers.filter((a) => a.isCorrect).map((a) => a.content)]))
const questionMapping: Record<string, Question> = Object.fromEntries(questions.map((q) => [q.id, q]))


function App() {
  const [form] = Form.useForm()
  const [formGithubId] = Form.useForm()
  const [wrongAnswers, setWrongAnswers] = React.useState<string[]>([])
  const [score, setScore] = React.useState<number>(-1)
  const [submitted, setSubmitted] = React.useState<boolean>(false)
  const [githubId, setGithubId] = React.useState<string>("")
  for (const q of questions) {
    q.answers = q.answers.sort(() => Math.random() - 0.5)
  }
  return (
    <>
      <section className="hero is-info">
        <div className="hero-body">
          <p className="title" style={{ marginBottom: 8 }}>OceanBase 知识挑战</p>
          <p className="subtitle">请选择你认为正确的答案，完成答题后点击【提交】</p>
        </div>

      </section>

      <div style={{
        margin: 'auto',
        paddingTop: '60px',
        paddingBottom: '60px',
        paddingLeft: '2%',
        paddingRight: '2%',
      }}>
       {!submitted && (<Form form={form} layout={'vertical'} size={'large'}>
          {questions.map((q, idx) =>
          
            <div style={{padding:25}} className="box" key={q.id}>
              {
                  //(<Typography.Text strong style={{paddingBottom:16}}>{`${idx + 1}. ${q.title}`}</Typography.Text>)
                 <div style={{marginBottom: 16}}><b>{`${idx + 1}. ${q.title}`}</b></div>
                }
              <Form.Item
                name={q.id}
                rules={[{ required: true, message: '请回答该问题' }]}
              >
                
                {
                  q.type === QuestionType.SingleChoice ?
                    (<Radio.Group>
                      <Space direction={'vertical'}>
                        {q.answers.map((a) => <Radio key={a.content} value={a.content}>{a.content}</Radio>)}
                      </Space>
                    </Radio.Group>) :
                    (<Checkbox.Group>
                      <Space direction={'vertical'}>
                        {q.answers.map((a) => <Checkbox key={a.content} value={a.content}>{a.content}</Checkbox>)}
                      </Space>
                    </Checkbox.Group>)
                }
              </Form.Item>
            </div>
          )}
        </Form>
       )}
       {!submitted && (<Form form={formGithubId} layout={'vertical'}>
          <div style={{paddingTop:25}} >
            <Form.Item name="githubIdFormValue" rules={[{ required: true, message: '请输入GitHub ID' }]}>
              <Input key="githubIdInputValue" value="githubIdInputValueName" placeholder="请输入你的github id" style={{ width: 200 }} />
            </Form.Item>
          </div>
        </Form>
       )}
        { !submitted && (
        <Space style={{ marginTop: 24 }}>
          
          <Button type="primary" onClick={async () => {
            const githubIdValue = await formGithubId.validateFields()
            setGithubId(githubIdValue.githubIdFormValue)

            const values = await form.validateFields()
            let score = 0
            const wrongAnswers: string[] = []
            for (const [id, answers] of Object.entries(values)) {
              const correct = correctMapping[id]
              if (typeof answers === 'string') {
                if (correct.includes(answers)) {
                  score += 5
                } else {
                  wrongAnswers.push(id)
                }
              } else if (Array.isArray(answers)) {
                if (correct.every((c) => answers.includes(c)) && correct.length === answers.length) {
                  score += 5
                } else {
                  wrongAnswers.push(id)
                }
              }
            }
            setWrongAnswers(wrongAnswers)
            setScore(score)
            setSubmitted(true)
            console.log("score", score)
            // message.info(`你的得分是 ${score}`)
          }}>提交</Button>
        </Space>
        )}
        {score >= 0 && (
          <div style={{ marginTop: 32 }}>
            <Typography.Title level={4}>{githubId} 你的得分是 {score}</Typography.Title>
          </div>
        )}
        {wrongAnswers.length > 0 && (
          <div style={{ marginTop: 32 }}>
            <Typography.Title level={4}>错误题目</Typography.Title>
            <ul>
              {wrongAnswers.map((id) => (
                <li key={id} style={{marginTop: 16}}>
                  <Typography.Title level={5}>{`${id}. ${questionMapping[id].title}`}</Typography.Title>
                  <ul>
                    {correctMapping[id].map((c) => (
                      <li key={c}>
                        ✅ <Typography.Text type={'success'}>{c}</Typography.Text>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </>
  )
}

export default App
